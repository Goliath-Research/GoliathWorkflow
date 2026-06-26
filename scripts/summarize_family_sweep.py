from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _series_summary(vals: pd.Series) -> dict[str, Any]:
    arr = pd.to_numeric(vals, errors="coerce").dropna().to_numpy(dtype=float)
    if arr.size == 0:
        return {
            "n": 0,
            "mean": None,
            "std": None,
            "q05": None,
            "q25": None,
            "q50": None,
            "q75": None,
            "q95": None,
            "ci95_low": None,
            "ci95_high": None,
        }
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
    se = std / np.sqrt(arr.size) if arr.size > 1 else 0.0
    ci = 1.96 * se
    return {
        "n": int(arr.size),
        "mean": mean,
        "std": std,
        "q05": float(np.quantile(arr, 0.05)),
        "q25": float(np.quantile(arr, 0.25)),
        "q50": float(np.quantile(arr, 0.50)),
        "q75": float(np.quantile(arr, 0.75)),
        "q95": float(np.quantile(arr, 0.95)),
        "ci95_low": float(mean - ci),
        "ci95_high": float(mean + ci),
    }


def _load_method_counts(path: Path) -> str:
    if not path.is_file():
        return ""
    payload = json.loads(path.read_text(encoding="utf-8"))
    counts = payload.get("counts") or {}
    parts = [f"{k}:{v}" for k, v in sorted(counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))]
    return "; ".join(parts)


def main() -> None:
    analysis_root = Path("/work/projects/prostate-cancer/Healthy_vs_PCa1-4-CG/model_family_analysis")
    candidates_root = analysis_root / "candidates"
    out_root = analysis_root / "reports"
    out_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []

    families = sorted([p for p in candidates_root.iterdir() if p.is_dir()])
    metric_by_family: dict[str, np.ndarray] = {}

    for fam_dir in families:
        fam_name = fam_dir.name.replace("_plus_", "+")
        all_metrics_path = fam_dir / "all_metrics.csv"
        if not all_metrics_path.is_file():
            continue
        df = pd.read_csv(all_metrics_path)
        if "balanced_accuracy" not in df.columns:
            continue

        ba = pd.to_numeric(df["balanced_accuracy"], errors="coerce").dropna()
        metric_by_family[fam_name] = ba.to_numpy(dtype=float)
        ba_summary = _series_summary(ba)

        macro_f1_summary = _series_summary(df.get("macro_f1", pd.Series(dtype=float)))
        acc_summary = _series_summary(df.get("accuracy", pd.Series(dtype=float)))

        rows.append(
            {
                "family_set": fam_name,
                "balanced_accuracy_mean": ba_summary["mean"],
                "balanced_accuracy_std": ba_summary["std"],
                "balanced_accuracy_q05": ba_summary["q05"],
                "balanced_accuracy_q25": ba_summary["q25"],
                "balanced_accuracy_q50": ba_summary["q50"],
                "balanced_accuracy_q75": ba_summary["q75"],
                "balanced_accuracy_q95": ba_summary["q95"],
                "balanced_accuracy_ci95_low": ba_summary["ci95_low"],
                "balanced_accuracy_ci95_high": ba_summary["ci95_high"],
                "macro_f1_mean": macro_f1_summary["mean"],
                "macro_f1_q50": macro_f1_summary["q50"],
                "accuracy_mean": acc_summary["mean"],
                "n_iterations": ba_summary["n"],
                "selected_methods": _load_method_counts(fam_dir / "selected_method_counts.json"),
            }
        )

    for a_name, a_vals in metric_by_family.items():
        for b_name, b_vals in metric_by_family.items():
            if a_name >= b_name:
                continue
            n = min(a_vals.size, b_vals.size)
            if n == 0:
                continue
            diff = a_vals[:n] - b_vals[:n]
            overlap_rows.append(
                {
                    "family_a": a_name,
                    "family_b": b_name,
                    "n_paired": int(n),
                    "mean_delta_ba_a_minus_b": float(np.mean(diff)),
                    "median_delta_ba_a_minus_b": float(np.median(diff)),
                    "p_a_gt_b": float(np.mean(diff > 0)),
                    "p_a_ge_b": float(np.mean(diff >= 0)),
                }
            )

    summary_df = pd.DataFrame(rows)
    if not summary_df.empty:
        summary_df.sort_values(
            ["balanced_accuracy_q50", "balanced_accuracy_mean"],
            ascending=[False, False],
            inplace=True,
        )
        summary_df.insert(0, "rank_by_ba_q50", list(range(1, len(summary_df) + 1)))
    summary_df.to_csv(out_root / "family_distribution_summary.csv", index=False)

    overlap_df = pd.DataFrame(overlap_rows)
    if not overlap_df.empty:
        overlap_df.sort_values(["p_a_gt_b", "mean_delta_ba_a_minus_b"], ascending=[False, False], inplace=True)
    overlap_df.to_csv(out_root / "family_pairwise_overlap.csv", index=False)

    payload = {
        "summary_csv": str((out_root / "family_distribution_summary.csv").resolve()),
        "overlap_csv": str((out_root / "family_pairwise_overlap.csv").resolve()),
        "n_families": int(summary_df["family_set"].nunique()) if not summary_df.empty else 0,
    }
    (out_root / "summary_manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
