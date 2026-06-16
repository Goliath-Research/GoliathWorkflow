#!/usr/bin/env python3
"""
Build flat alignment-QC metric tables per group and compare groups.

Each group is a CSV with a sample_id column (or first column). QC JSONs are read
from --qc-dir (default /work/AlignmentQC/{sample_id}.json).

Outputs under --out:
  - all_samples_qc_flat.csv
  - group_summary_stats.csv  (mean/std/median per metric per group)
  - group_comparison.csv     (pairwise mean deltas for numeric metrics)

Example:
  python scripts/compare_alignment_qc_groups.py \\
    --group healthy --samples-csv /path/healthy_samples.csv \\
    --group PCa --samples-csv /path/pca_samples.csv \\
    --out /work/AlignmentQC/group_comparison/pca_vs_healthy
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

DEFAULT_QC_DIR = "/work/AlignmentQC"

GUARDRAIL_SCALAR_KEYS = (
    "pf_percent",
    "q30_percent",
    "mean_quality",
    "min_quality_post20",
    "at_dropout",
    "gc_dropout",
    "median_insert_bp",
    "deamination_qscore",
    "oxog_qscore",
)


def _load_sample_ids(csv_path: Path) -> List[str]:
    df = pd.read_csv(csv_path)
    col = "sample_id" if "sample_id" in df.columns else df.columns[0]
    ids: List[str] = []
    seen: set[str] = set()
    for raw in df[col].astype(str):
        sid = raw.strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        ids.append(sid)
    return ids


def _guardrail_value(details: Dict[str, Any], key: str) -> Tuple[Optional[float], Optional[bool]]:
    node = details.get(key)
    if not isinstance(node, dict):
        return None, None
    val = node.get("value")
    passed = node.get("pass")
    try:
        fval = float(val) if val is not None else None
    except (TypeError, ValueError):
        fval = None
    pbool = bool(passed) if passed is not None else None
    return fval, pbool


def flatten_qc_json(qc_path: Path) -> Dict[str, Any]:
    payload = json.loads(qc_path.read_text(encoding="utf-8"))
    row: Dict[str, Any] = {
        "qc_json_sample_id": payload.get("sample_id") or qc_path.stem,
    }

    summary = payload.get("summary_stats") or {}
    for k, v in summary.items():
        row[f"summary_{k}"] = v

    qy = payload.get("quality_yield") or {}
    for k in ("total_reads", "pf_reads", "pf_bases", "q30_bases", "pf_q30_bases"):
        if k in qy:
            row[f"quality_yield_{k}"] = qy[k]
    if qy.get("pf_bases") and qy.get("total_bases"):
        row["quality_yield_pf_fraction"] = float(qy["pf_bases"]) / float(qy["total_bases"])
    if qy.get("pf_q30_bases") and qy.get("pf_bases"):
        row["quality_yield_pf_q30_fraction"] = float(qy["pf_q30_bases"]) / float(qy["pf_bases"])

    guardrails = payload.get("guardrails") or {}
    row["guardrails_overall_pass"] = guardrails.get("overall_pass")
    screening = guardrails.get("screening") or {}
    row["screening_disposition"] = screening.get("disposition")
    row["trim_front2"] = screening.get("trim_front2")
    row["screening_message"] = screening.get("message")
    details = guardrails.get("details") or {}
    for key in GUARDRAIL_SCALAR_KEYS:
        val, passed = _guardrail_value(details, key)
        row[f"guardrail_{key}"] = val
        row[f"guardrail_{key}_pass"] = passed

    frag = payload.get("fragmentomics_metrics") or {}
    for k in ("median_insert_bp", "nucleosome_peak_bp", "short_fragment_fraction"):
        if k in frag:
            row[f"fragmentomics_{k}"] = frag[k]

    return row


def load_group_rows(
    group_name: str,
    sample_ids: Iterable[str],
    qc_dir: Path,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sid in sample_ids:
        qc_path = qc_dir / f"{sid}.json"
        base = {"group": group_name, "sample_id": sid, "qc_json": str(qc_path)}
        if not qc_path.is_file():
            rows.append({**base, "qc_status": "missing"})
            continue
        try:
            flat = flatten_qc_json(qc_path)
            row = {**base, "qc_status": "ok", **flat}
            # Canonical sample_id comes from the group CSV / filename, not JSON payload.
            row["sample_id"] = sid
            rows.append(row)
        except (json.JSONDecodeError, OSError) as exc:
            rows.append({**base, "qc_status": f"error:{exc}"})
    return rows


def _numeric_metric_columns(df: pd.DataFrame) -> List[str]:
    skip = {"sample_id", "group", "qc_json", "qc_status", "guardrails_overall_pass"}
    cols: List[str] = []
    for col in df.columns:
        if col in skip or col.endswith("_pass"):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols


def summarize_groups(df: pd.DataFrame) -> pd.DataFrame:
    metric_cols = _numeric_metric_columns(df)
    ok = df[df["qc_status"] == "ok"]
    rows: List[Dict[str, Any]] = []
    for group, sub in ok.groupby("group"):
        for col in metric_cols:
            series = pd.to_numeric(sub[col], errors="coerce").dropna()
            if series.empty:
                continue
            rows.append(
                {
                    "group": group,
                    "metric": col,
                    "n": int(series.shape[0]),
                    "mean": float(series.mean()),
                    "std": float(series.std(ddof=1)) if series.shape[0] > 1 else 0.0,
                    "median": float(series.median()),
                    "min": float(series.min()),
                    "max": float(series.max()),
                }
            )
    return pd.DataFrame(rows)


def compare_groups(summary: pd.DataFrame) -> pd.DataFrame:
    groups = sorted(summary["group"].unique())
    rows: List[Dict[str, Any]] = []
    for i, ga in enumerate(groups):
        for gb in groups[i + 1 :]:
            a = summary[summary["group"] == ga].set_index("metric")
            b = summary[summary["group"] == gb].set_index("metric")
            for metric in sorted(set(a.index) & set(b.index)):
                rows.append(
                    {
                        "group_a": ga,
                        "group_b": gb,
                        "metric": metric,
                        "mean_a": a.loc[metric, "mean"],
                        "mean_b": b.loc[metric, "mean"],
                        "mean_delta_a_minus_b": float(a.loc[metric, "mean"] - b.loc[metric, "mean"]),
                        "median_a": a.loc[metric, "median"],
                        "median_b": b.loc[metric, "median"],
                        "n_a": int(a.loc[metric, "n"]),
                        "n_b": int(b.loc[metric, "n"]),
                    }
                )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qc-dir",
        type=Path,
        default=Path(DEFAULT_QC_DIR),
        help=f"Directory with {{sample_id}}.json files (default: {DEFAULT_QC_DIR})",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        metavar="NAME",
        help="Group label; pair with --samples-csv (repeat for multiple groups)",
    )
    parser.add_argument(
        "--samples-csv",
        action="append",
        default=[],
        help="CSV listing sample_id per group; order must match repeated --group",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    args = parser.parse_args()

    if len(args.group) != len(args.samples_csv):
        raise SystemExit("Provide the same number of --group and --samples-csv arguments")
    if not args.group:
        raise SystemExit("At least one --group and --samples-csv pair is required")

    all_rows: List[Dict[str, Any]] = []
    for group_name, csv_path in zip(args.group, args.samples_csv):
        sample_ids = _load_sample_ids(Path(csv_path))
        all_rows.extend(load_group_rows(group_name, sample_ids, args.qc_dir))

    args.out.mkdir(parents=True, exist_ok=True)
    flat_df = pd.DataFrame(all_rows)
    flat_df.to_csv(args.out / "all_samples_qc_flat.csv", index=False)

    summary_df = summarize_groups(flat_df)
    summary_df.to_csv(args.out / "group_summary_stats.csv", index=False)
    compare_df = compare_groups(summary_df)
    compare_df.to_csv(args.out / "group_comparison.csv", index=False)

    missing = flat_df[flat_df["qc_status"] != "ok"]
    if not missing.empty:
        missing.to_csv(args.out / "samples_missing_qc_in_groups.csv", index=False)

    print(f"Wrote {args.out}/all_samples_qc_flat.csv ({flat_df.shape[0]} rows)")
    print(f"Wrote {args.out}/group_summary_stats.csv")
    print(f"Wrote {args.out}/group_comparison.csv")
    if not missing.empty:
        print(f"Warning: {missing.shape[0]} group samples missing QC JSON — see samples_missing_qc_in_groups.csv")


if __name__ == "__main__":
    main()
