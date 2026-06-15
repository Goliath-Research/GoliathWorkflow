#!/usr/bin/env python3
"""
Audit alignment QC JSON coverage for sample directories.

Compares sample folders under --samples-base (default /work/samples) against
QC JSON files in --qc-dir (default /work/AlignmentQC).

Writes:
  - coverage_summary.json
  - samples_with_qc.csv
  - samples_missing_qc.csv  (with reason: no_metrics | metrics_present)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

DEFAULT_SAMPLES_BASE = "/work/samples"
DEFAULT_QC_DIR = "/work/AlignmentQC"


def _has_metrics(sample_dir: Path) -> bool:
    if not sample_dir.is_dir():
        return False
    for pattern in ("*deduplicate_metrics.txt", "*.deduplicate_metrics.txt"):
        if list(sample_dir.glob(pattern)) or list(sample_dir.rglob(pattern)):
            return True
    return False


def audit(samples_base: Path, qc_dir: Path) -> Dict[str, Any]:
    sample_dirs = sorted(p for p in samples_base.iterdir() if p.is_dir())
    qc_json = {
        p.stem
        for p in qc_dir.glob("*.json")
        if p.is_file() and not p.name.endswith(".v2.json")
    }

    rows: List[Dict[str, Any]] = []
    for sample_dir in sample_dirs:
        name = sample_dir.name
        has_metrics = _has_metrics(sample_dir)
        has_qc = name in qc_json
        if has_qc:
            status = "ok"
            reason = ""
        elif has_metrics:
            status = "missing_qc"
            reason = "metrics_present"
        else:
            status = "missing_qc"
            reason = "no_metrics"
        rows.append(
            {
                "sample_id": name,
                "sample_dir": str(sample_dir),
                "has_qc_json": has_qc,
                "has_metrics": has_metrics,
                "status": status,
                "reason": reason,
            }
        )

    df = pd.DataFrame(rows)
    ok = df[df["status"] == "ok"]
    missing = df[df["status"] == "missing_qc"]
    missing_metrics = missing[missing["reason"] == "metrics_present"]
    missing_no_metrics = missing[missing["reason"] == "no_metrics"]

    summary = {
        "samples_base": str(samples_base),
        "qc_dir": str(qc_dir),
        "n_sample_dirs": len(sample_dirs),
        "n_with_qc_json": int(ok.shape[0]),
        "n_missing_qc": int(missing.shape[0]),
        "n_missing_qc_with_metrics": int(missing_metrics.shape[0]),
        "n_missing_qc_no_metrics": int(missing_no_metrics.shape[0]),
        "n_extra_qc_json": int(len(qc_json - {p.name for p in sample_dirs})),
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples-base",
        type=Path,
        default=Path(DEFAULT_SAMPLES_BASE),
        help=f"Sample directory root (default: {DEFAULT_SAMPLES_BASE})",
    )
    parser.add_argument(
        "--qc-dir",
        type=Path,
        default=Path(DEFAULT_QC_DIR),
        help=f"Alignment QC JSON output dir (default: {DEFAULT_QC_DIR})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for audit CSV/JSON",
    )
    args = parser.parse_args()

    result = audit(args.samples_base, args.qc_dir)
    args.out.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(result["rows"])
    df.to_csv(args.out / "alignment_qc_coverage.csv", index=False)
    df[df["status"] == "ok"].to_csv(args.out / "samples_with_qc.csv", index=False)
    df[df["status"] == "missing_qc"].to_csv(args.out / "samples_missing_qc.csv", index=False)
    (args.out / "coverage_summary.json").write_text(
        json.dumps(result["summary"], indent=2) + "\n",
        encoding="utf-8",
    )

    s = result["summary"]
    print(json.dumps(s, indent=2))
    print(f"Wrote {args.out}/alignment_qc_coverage.csv")


if __name__ == "__main__":
    main()
