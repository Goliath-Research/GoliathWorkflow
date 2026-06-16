#!/usr/bin/env python3
"""
Cohort alignment QC screening report from existing V2 JSON exports.

Re-runs cycle-quality screening on guardrails + mean_quality_by_cycle without re-alignment.
Outputs summary JSON and remediation/investigate CSV manifests.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from methyl_alignment_qc.core.cycle_quality_screening import failed_guardrail_keys, screen_cycle_quality
from methyl_alignment_qc.models.config import CycleScreeningConfig, OptionalGuardrailsConfig
from methyl_alignment_qc.core.wgbs_parabricks_qc import apply_optional_guardrails

DEFAULT_QC_DIR = "/work/AlignmentQC"
BATCH_PREFIXES = ("DBCST", "HBCST", "5929", "1401")


def _load_sample_ids(csv_path: Path) -> List[str]:
    import pandas as pd

    df = pd.read_csv(csv_path)
    col = "sample_id" if "sample_id" in df.columns else df.columns[0]
    ids: List[str] = []
    seen: set[str] = set()
    for raw in df[col].astype(str):
        sid = raw.strip()
        if sid and sid not in seen:
            seen.add(sid)
            ids.append(sid)
    return ids


def _batch_prefix(sample_id: str) -> str:
    for prefix in BATCH_PREFIXES:
        if sample_id.startswith(prefix):
            return prefix
    m = re.match(r"^(\d{4})", sample_id)
    return m.group(1) if m else "other"


def _v1_payload_from_v2(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal V1-shaped dict for screening from V2 export."""
    payload: Dict[str, Any] = dict(raw)
    mqc = raw.get("mean_quality_by_cycle") or {}
    if "rows" in mqc:
        rows = mqc["rows"]
        payload["mean_quality_by_cycle"] = {
            "cycle": [r["cycle"] for r in rows],
            "mean_quality": [r["mean_quality"] for r in rows],
        }
    return payload


def screen_one_qc_json(
    qc_path: Path,
    *,
    cycle_cfg: CycleScreeningConfig,
    opt_cfg: OptionalGuardrailsConfig,
) -> Dict[str, Any]:
    raw = json.loads(qc_path.read_text(encoding="utf-8"))
    payload = _v1_payload_from_v2(raw)
    guardrails = dict(raw.get("guardrails") or {})
    apply_optional_guardrails(
        guardrails,
        payload,
        duplication_rate_max=opt_cfg.duplication_rate_max,
        min_pf_reads=opt_cfg.min_pf_reads,
    )
    screening = screen_cycle_quality(payload, guardrails, cycle_cfg)
    return {
        "sample_id": raw.get("sample_id") or qc_path.stem,
        "qc_path": str(qc_path),
        "overall_pass": guardrails.get("overall_pass"),
        "screening": screening,
        "failed_guardrails": failed_guardrail_keys(guardrails),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qc-dir", type=Path, default=Path(DEFAULT_QC_DIR))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--group", action="append", default=[], metavar="NAME=CSV")
    parser.add_argument("--read-length", type=int, default=None)
    args = parser.parse_args()

    groups: Dict[str, List[str]] = {}
    for spec in args.group:
        name, _, csv_path = spec.partition("=")
        if not csv_path:
            raise SystemExit(f"Invalid --group {spec!r}; use NAME=path/to.csv")
        groups[name.strip()] = _load_sample_ids(Path(csv_path))

    if not groups:
        groups["all"] = [p.stem for p in sorted(args.qc_dir.glob("*.json"))]

    cycle_cfg = CycleScreeningConfig(read_length=args.read_length)
    opt_cfg = OptionalGuardrailsConfig()

    records: List[Dict[str, Any]] = []
    for group_name, sample_ids in groups.items():
        for sid in sample_ids:
            qc_path = args.qc_dir / f"{sid}.json"
            if not qc_path.is_file():
                records.append(
                    {
                        "sample_id": sid,
                        "group": group_name,
                        "qc_path": str(qc_path),
                        "status": "missing",
                    }
                )
                continue
            row = screen_one_qc_json(qc_path, cycle_cfg=cycle_cfg, opt_cfg=opt_cfg)
            row["group"] = group_name
            row["status"] = "ok"
            row["batch_prefix"] = _batch_prefix(sid)
            records.append(row)

    args.out.mkdir(parents=True, exist_ok=True)

    disposition_counts: Counter[str] = Counter()
    group_disposition: Dict[str, Counter[str]] = defaultdict(Counter)
    batch_trim: Dict[str, List[int]] = defaultdict(list)

    remediation_rows: List[Dict[str, Any]] = []
    investigate_rows: List[Dict[str, Any]] = []

    for rec in records:
        if rec.get("status") != "ok":
            continue
        screening = rec.get("screening") or {}
        disp = str(screening.get("disposition") or "UNKNOWN")
        disposition_counts[disp] += 1
        group_disposition[rec["group"]][disp] += 1
        trim = int(screening.get("trim_front2") or 0)
        if trim > 0:
            batch_trim[rec.get("batch_prefix", "other")].append(trim)
        if disp == "REALIGN_READ2_TRIM":
            remediation_rows.append(
                {
                    "sample_id": rec["sample_id"],
                    "group": rec["group"],
                    "disposition": disp,
                    "trim_front2": trim,
                    "qc_path": rec["qc_path"],
                }
            )
        elif disp in ("INVESTIGATE_MULTI_REGION", "INVESTIGATE_GUARDRAIL_ONLY", "NOT_FIXABLE"):
            investigate_rows.append(
                {
                    "sample_id": rec["sample_id"],
                    "group": rec["group"],
                    "disposition": disp,
                    "failed_guardrails": ";".join(rec.get("failed_guardrails") or []),
                    "qc_path": rec["qc_path"],
                    "message": screening.get("message"),
                }
            )

    batch_summary = []
    for prefix, trims in sorted(batch_trim.items()):
        if not trims:
            continue
        batch_summary.append(
            {
                "batch_prefix": prefix,
                "n_samples": len(trims),
                "median_trim_front2": sorted(trims)[len(trims) // 2],
                "min_trim_front2": min(trims),
                "max_trim_front2": max(trims),
            }
        )

    summary = {
        "qc_dir": str(args.qc_dir),
        "n_records": len(records),
        "disposition_counts": dict(disposition_counts),
        "group_disposition_counts": {g: dict(c) for g, c in group_disposition.items()},
        "batch_trim_summary": batch_summary,
    }
    (args.out / "cohort_screening_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    with open(args.out / "remediation_manifest.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["sample_id", "group", "disposition", "trim_front2", "qc_path"])
        writer.writeheader()
        writer.writerows(remediation_rows)

    with open(args.out / "investigate_manifest.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["sample_id", "group", "disposition", "failed_guardrails", "qc_path", "message"],
        )
        writer.writeheader()
        writer.writerows(investigate_rows)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
