"""
Read validation_metrics.json, flatten to one row per run, and compute empirical distribution summary.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

# Scalar metric keys we want in the flat table and in the summary (skip nested per_class, confusion_matrix)
SCALAR_KEYS = [
    "accuracy",
    "balanced_accuracy",
    "sensitivity",
    "specificity",
    "macro_precision",
    "macro_recall",
    "macro_f1",
    "weighted_f1",
    "precision_binary",
    "recall_binary",
    "f1_binary",
    "n_samples",
    "n_classes",
]


def _scalar_metrics_from_dict(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Extract scalar metrics from a validation_metrics dict (skip lists/nested)."""
    out: Dict[str, Any] = {}
    for k in SCALAR_KEYS:
        if k in metrics and isinstance(metrics[k], (int, float)):
            out[k] = metrics[k]
    return out


def load_metrics_from_json(path: str | Path) -> Dict[str, Any]:
    """Load a single validation_metrics.json file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_metrics_table(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame from a list of row dicts (each has iteration, run_dir, and scalar metrics)."""
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def write_all_metrics_csv(df: pd.DataFrame, path: str | Path) -> None:
    """Write the raw metrics table to CSV (one row per iteration)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def build_step_timings_table(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame from step timing rows (step_name, duration_seconds, return_code, optional run_id, run_dir, n_train_samples, n_val_samples)."""
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def write_step_timings_csv(df_or_rows: pd.DataFrame | List[Dict[str, Any]], path: str | Path) -> None:
    """Write step timings to CSV. Accepts a DataFrame or a list of row dicts."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if isinstance(df_or_rows, pd.DataFrame):
        df_or_rows.to_csv(path, index=False)
    else:
        pd.DataFrame(df_or_rows).to_csv(path, index=False)


def compute_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute per-metric empirical distribution: mean, std, min, max, and percentiles (5, 25, 50, 75, 95).
    Only numeric columns are summarized.
    """
    summary: Dict[str, Any] = {}
    percentiles = [5, 25, 50, 75, 95]
    for col in df.select_dtypes(include=[np.number]).columns:
        series = df[col].dropna()
        if len(series) == 0:
            continue
        summary[col] = {
            "mean": float(series.mean()),
            "std": float(series.std()) if len(series) > 1 else 0.0,
            "min": float(series.min()),
            "max": float(series.max()),
            "count": int(len(series)),
        }
        try:
            p = np.percentile(series, percentiles)
            summary[col]["percentiles"] = {f"p{pct}": float(v) for pct, v in zip(percentiles, p)}
        except Exception:
            pass
    return summary


def write_summary_json(summary: Dict[str, Any], path: str | Path) -> None:
    """Write the summary dict to JSON."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
