"""
Stability analysis for discovery pipeline outputs across Monte Carlo runs.

Computes frequency of DMPs and genes across runs, produces stable panels
that can be used for production MethylClassifier / MethylPredictor.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def load_discovery_dmps(run_dir: Path) -> Optional[pd.DataFrame]:
    """Load dmps-*-discovery.csv from a MC run directory."""
    detection_dirs = list(run_dir.glob("**/detections/*/*"))
    if not detection_dirs:
        detection_dirs = list(run_dir.glob("detections/*/*"))
    for d in detection_dirs:
        for csv in d.glob("dmps-*-discovery.csv"):
            try:
                return pd.read_csv(csv)
            except Exception:
                continue
    return None


def load_enricher_genes(run_dir: Path) -> Optional[pd.DataFrame]:
    """Load enricher gene output (all-gene_name-combined.csv or similar)."""
    enricher_dirs = list(run_dir.glob("**/enricher/*/*")) or list(run_dir.glob("enricher/*/*"))
    for d in enricher_dirs:
        for csv in d.glob("*gene*.csv"):
            try:
                df = pd.read_csv(csv)
                if "gene_name" in df.columns:
                    return df
            except Exception:
                continue
    return None


def compute_dmp_stability(
    monte_carlo_runs_root: Path, min_frequency: float = 0.7
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Count how often each DMP appears in discovery CSVs across runs.
    Returns (frequency_df, summary).
    """
    runs = sorted(monte_carlo_runs_root.glob("run_*"))
    if not runs:
        runs = sorted(monte_carlo_runs_root.glob("run_0*"))

    dmp_counts: Dict[Tuple[int, str], int] = defaultdict(int)
    run_count = 0

    for run_dir in runs:
        df = load_discovery_dmps(run_dir)
        if df is None or "position" not in df.columns or "chromosome" not in df.columns:
            continue
        run_count += 1
        for _, row in df.iterrows():
            key = (int(row["chromosome"]), int(row["position"]))
            dmp_counts[key] += 1

    if run_count == 0:
        return pd.DataFrame(), {}

    data = []
    for (chrom, pos), count in dmp_counts.items():
        freq = count / run_count
        data.append({
            "chromosome": chrom,
            "position": pos,
            "frequency": freq,
            "count": count,
            "n_runs": run_count,
        })

    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values("frequency", ascending=False)

    stable = df[df["frequency"] >= min_frequency] if not df.empty else pd.DataFrame()
    summary = {
        "n_runs_analyzed": run_count,
        "total_unique_dmps": len(dmp_counts),
        "stable_dmps_at_threshold": len(stable),
        "min_frequency": min_frequency,
        "stable_dmp_fraction": len(stable) / len(dmp_counts) if len(dmp_counts) > 0 else 0.0,
    }

    return df, summary


def compute_gene_stability(
    monte_carlo_runs_root: Path, min_frequency: float = 0.5
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Count gene appearance frequency from enricher outputs."""
    runs = sorted(monte_carlo_runs_root.glob("run_*"))
    gene_counts: Counter = Counter()
    run_count = 0

    for run_dir in runs:
        df = load_enricher_genes(run_dir)
        if df is None or "gene_name" not in df.columns:
            continue
        run_count += 1
        for gene in df["gene_name"].dropna().astype(str):
            gene_counts[gene.strip()] += 1

    if run_count == 0:
        return pd.DataFrame(), {}

    data = []
    for gene, count in gene_counts.items():
        freq = count / run_count
        data.append({"gene_name": gene, "frequency": freq, "count": count, "n_runs": run_count})

    df = pd.DataFrame(data).sort_values("frequency", ascending=False)

    stable = df[df["frequency"] >= min_frequency] if not df.empty else pd.DataFrame()
    summary = {
        "n_runs_analyzed": run_count,
        "total_unique_genes": len(gene_counts),
        "stable_genes_at_threshold": len(stable),
        "min_frequency": min_frequency,
    }

    return df, summary


def write_stable_panel(
    dmp_freq_df: pd.DataFrame,
    output_dir: Path,
    min_frequency: float = 0.7,
    top_n: Optional[int] = None,
) -> Path:
    """Write stable DMPs as a production classifier panel."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stable = dmp_freq_df[dmp_freq_df["frequency"] >= min_frequency].copy()

    if top_n is not None and len(stable) > top_n:
        stable = stable.head(top_n)

    out_path = output_dir / "stable_dmps_production.csv"
    stable.to_csv(out_path, index=False)
    return out_path


def run_stability_analysis(
    monte_carlo_runs_root: Path,
    output_dir: Optional[Path] = None,
    dmp_min_freq: float = 0.7,
    gene_min_freq: float = 0.5,
    top_n_dmps: Optional[int] = None,
) -> Dict[str, Any]:
    """Main entry point for stability analysis."""
    if output_dir is None:
        output_dir = monte_carlo_runs_root / "stability"

    dmp_df, dmp_summary = compute_dmp_stability(monte_carlo_runs_root, dmp_min_freq)
    gene_df, gene_summary = compute_gene_stability(monte_carlo_runs_root, gene_min_freq)

    stable_dmp_path = None
    if not dmp_df.empty:
        stable_dmp_path = write_stable_panel(dmp_df, output_dir, dmp_min_freq, top_n_dmps)

    summary = {
        "dmp_stability": dmp_summary,
        "gene_stability": gene_summary,
        "stable_dmp_csv": str(stable_dmp_path) if stable_dmp_path else None,
        "output_dir": str(output_dir),
    }

    summary_path = output_dir / "stability_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    if not dmp_df.empty:
        dmp_df.to_csv(output_dir / "dmp_frequency.csv", index=False)
    if not gene_df.empty:
        gene_df.to_csv(output_dir / "gene_frequency.csv", index=False)

    return summary
