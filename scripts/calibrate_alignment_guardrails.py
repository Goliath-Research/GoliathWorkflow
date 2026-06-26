#!/usr/bin/env python3
"""
Summarize alignment-layer metrics from alignment QC JSON exports for threshold tuning.

Reads {sample_id}.json files from --qc-dir, computes or reuses alignment_stats, and
prints per-metric percentiles plus suggested guardrail defaults.

Example:
  source .venv/bin/activate
  python scripts/calibrate_alignment_guardrails.py \\
    --qc-dir /work/projects/prostate-cancer/alignment_qc
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "methylalignmentqc"))

from methyl_alignment_qc.core.alignment_derived_qc import compute_alignment_stats  # noqa: E402

METRIC_KEYS = (
    "mapping_rate",
    "secondary_supplementary_rate",
    "gc_coverage_uniformity",
    "properly_paired_rate",
    "supplementary_rate",
)


def _alignment_row(payload: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {"sample_id": payload.get("sample_id")}
    stats = payload.get("alignment_stats")
    if not isinstance(stats, dict):
        stats = compute_alignment_stats(payload)
    if isinstance(stats, dict):
        for k in ("mapping_rate", "secondary_supplementary_rate", "gc_coverage_uniformity"):
            if k in stats:
                row[k] = stats[k]
    flagstat = payload.get("alignment_flagstat") or {}
    if isinstance(flagstat, dict):
        for k in ("properly_paired_rate", "supplementary_rate"):
            if k in flagstat:
                row[k] = flagstat[k]
    return row


def _suggest_thresholds(series: pd.Series, *, higher_is_better: bool) -> Dict[str, float]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return {}
    p5, p50, p95 = float(clean.quantile(0.05)), float(clean.median()), float(clean.quantile(0.95))
    if higher_is_better:
        suggested = round(p5, 4)
    else:
        suggested = round(p95, 4)
    return {"p5": p5, "p50": p50, "p95": p95, "suggested": suggested}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qc-dir", type=Path, required=True, help="Directory with per-sample QC JSON files")
    parser.add_argument("--limit", type=int, default=0, help="Optional max files to read (0 = all)")
    args = parser.parse_args()

    qc_dir = args.qc_dir
    if not qc_dir.is_dir():
        raise SystemExit(f"QC directory not found: {qc_dir}")

    rows: List[Dict[str, Any]] = []
    for i, path in enumerate(sorted(qc_dir.glob("*.json"))):
        if args.limit and i >= args.limit:
            break
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        row = _alignment_row(payload)
        row["sample_id"] = row.get("sample_id") or path.stem
        rows.append(row)

    if not rows:
        raise SystemExit(f"No QC JSON files found under {qc_dir}")

    df = pd.DataFrame(rows)
    print(f"Samples: {len(df)} from {qc_dir}\n")

    suggestions = {
        "mapping_rate": True,
        "secondary_supplementary_rate": False,
        "gc_coverage_uniformity": True,
        "properly_paired_rate": True,
        "supplementary_rate": False,
    }
    for key in METRIC_KEYS:
        if key not in df.columns:
            continue
        stats = _suggest_thresholds(df[key], higher_is_better=suggestions[key])
        if not stats:
            continue
        direction = ">=" if suggestions[key] else "<="
        print(
            f"{key}: p5={stats['p5']:.4f} p50={stats['p50']:.4f} p95={stats['p95']:.4f} "
            f"suggested {direction} {stats['suggested']}"
        )

    print("\nProfile defaults in analyte_profiles (if cohort tails are tight):")
    print("  min_mapping_rate: 0.98")
    print("  max_secondary_supplementary_rate: 0.05")
    print("  min_gc_coverage_uniformity: (opt-in — calibrate from cohort p5)")
    print("  min_properly_paired_rate: 0.90")
    print("  max_supplementary_rate_flagstat: 0.02")


if __name__ == "__main__":
    main()
