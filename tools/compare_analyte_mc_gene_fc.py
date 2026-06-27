#!/usr/bin/env python3
"""
Compare MC gene FeatureCuts panels between plasma and buffy-coat project runs.

Scans monte_carlo_runs/run_*/gene_stability/ and stability/gene_frequency.csv per analyte,
then emits cross-analyte overlap tables and a decision-oriented summary.

Small-N warning: balanced_accuracy=1.0 on MC validation splits is feasibility-only at n~15/arm.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _load_gene_list(path: Path, gene_column: str = "gene_name") -> Set[str]:
    if not path.is_file():
        return set()
    df = pd.read_csv(path)
    col = gene_column if gene_column in df.columns else df.columns[0]
    genes = df[col].dropna().astype(str).str.strip()
    return set(genes[genes != ""].unique())


def _load_metrics(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _scan_mc_runs(project_root: Path) -> List[Dict[str, Any]]:
    mc_root = project_root / "monte_carlo_runs"
    runs: List[Dict[str, Any]] = []
    for run_dir in sorted(mc_root.glob("run_*")):
        gs = run_dir / "gene_stability"
        metrics_path = gs / "gene_featurecuts_metrics.json"
        genes_path = gs / "genes-classifier.csv"
        if not metrics_path.is_file() and not genes_path.is_file():
            continue
        metrics = _load_metrics(metrics_path)
        genes = _load_gene_list(genes_path)
        runs.append(
            {
                "run_id": run_dir.name,
                "run_dir": str(run_dir.resolve()),
                "balanced_accuracy": metrics.get("balanced_accuracy"),
                "selected_k": metrics.get("selected_k", len(genes)),
                "n_mapper_genes": metrics.get("n_mapper_genes_before_biomarker_filter"),
                "genes": genes,
            }
        )
    return runs


def _load_gene_frequency(project_root: Path, min_frequency: float) -> pd.DataFrame:
    path = project_root / "monte_carlo_runs" / "stability" / "gene_frequency.csv"
    if not path.is_file():
        return pd.DataFrame(columns=["gene_name", "frequency", "count", "n_runs"])
    df = pd.read_csv(path)
    if "gene_name" not in df.columns:
        return pd.DataFrame(columns=["gene_name", "frequency", "count", "n_runs"])
    return df[df["frequency"].astype(float) >= min_frequency].copy()


def _recurrent_gene_sets(
    freq_df: pd.DataFrame,
    *,
    min_frequency: float,
) -> Set[str]:
    if freq_df.empty:
        return set()
    return set(freq_df["gene_name"].astype(str).str.strip())


def _score_analytes(
    *,
    buffy_runs: List[Dict[str, Any]],
    plasma_runs: List[Dict[str, Any]],
    buffy_recurrent: Set[str],
    plasma_recurrent: Set[str],
    shared_recurrent: Set[str],
    mean_ba_buffy: Optional[float],
    mean_ba_plasma: Optional[float],
) -> Dict[str, Any]:
    """Weighted rubric scores (1–5) for analyte selection; BA down-weighted."""

    def recurrence_score(n_genes: int, n_runs: int, expected_runs: int) -> float:
        run_frac = n_runs / expected_runs if expected_runs else 0.0
        gene_norm = min(n_genes / 200.0, 1.0)
        raw = 0.6 * run_frac + 0.4 * gene_norm
        return max(1.0, min(5.0, 1.0 + raw * 4.0))

    expected = max(len(buffy_runs), len(plasma_runs), 1)
    buffy_n_runs = len(buffy_runs)
    plasma_n_runs = len(plasma_runs)

    buffy_recurrence = recurrence_score(len(buffy_recurrent), buffy_n_runs, expected)
    plasma_recurrence = recurrence_score(len(plasma_recurrent), plasma_n_runs, expected)

    concordance = _jaccard(buffy_recurrent, plasma_recurrent)
    concordance_score = max(1.0, min(5.0, 1.0 + concordance * 4.0))

    scores = {
        "buffy_coat": {
            "mc_gene_recurrence": round(buffy_recurrence, 2),
            "cross_analyte_concordance": round(concordance_score, 2),
            "mean_balanced_accuracy_mc": mean_ba_buffy,
            "recurrent_gene_count": len(buffy_recurrent),
            "mc_runs_with_panels": buffy_n_runs,
        },
        "cfdna": {
            "mc_gene_recurrence": round(plasma_recurrence, 2),
            "cross_analyte_concordance": round(concordance_score, 2),
            "mean_balanced_accuracy_mc": mean_ba_plasma,
            "recurrent_gene_count": len(plasma_recurrent),
            "mc_runs_with_panels": plasma_n_runs,
        },
    }
    weights = {"mc_gene_recurrence": 0.5, "cross_analyte_concordance": 0.3, "mean_balanced_accuracy_mc": 0.2}

    def weighted_total(side: str) -> float:
        s = scores[side]
        ba = s.get("mean_balanced_accuracy_mc")
        ba_component = (float(ba) * 5.0) if ba is not None else 2.5
        return (
            weights["mc_gene_recurrence"] * s["mc_gene_recurrence"]
            + weights["cross_analyte_concordance"] * s["cross_analyte_concordance"]
            + weights["mean_balanced_accuracy_mc"] * ba_component
        )

    buffy_total = weighted_total("buffy_coat")
    plasma_total = weighted_total("cfdna")
    if buffy_total > plasma_total:
        recommendation = "buffy_coat"
    elif plasma_total > buffy_total:
        recommendation = "cfdna"
    else:
        recommendation = "tie"

    return {
        "weights": weights,
        "scores": scores,
        "shared_recurrent_genes": len(shared_recurrent),
        "recurrent_jaccard": concordance,
        "weighted_total": {"buffy_coat": round(buffy_total, 3), "cfdna": round(plasma_total, 3)},
        "recommended_analyte": recommendation,
        "small_n_warning": (
            "MC validation BA at n~15/arm is feasibility-only; prioritize gene recurrence and "
            "cross-analyte concordance over perfect BA."
        ),
    }


def compare_mc_gene_fc(
    plasma_root: Path,
    buffy_root: Path,
    *,
    min_frequency: float = 0.7,
    comparison: str = "all/PCa",
) -> Dict[str, Any]:
    plasma_root = plasma_root.expanduser().resolve()
    buffy_root = buffy_root.expanduser().resolve()

    plasma_runs = _scan_mc_runs(plasma_root)
    buffy_runs = _scan_mc_runs(buffy_root)

    plasma_by_id = {r["run_id"]: r for r in plasma_runs}
    buffy_by_id = {r["run_id"]: r for r in buffy_runs}
    all_run_ids = sorted(set(plasma_by_id) | set(buffy_by_id))

    overlap_rows: List[Dict[str, Any]] = []
    all_plasma_genes: Set[str] = set()
    all_buffy_genes: Set[str] = set()
    for run_id in all_run_ids:
        p = plasma_by_id.get(run_id, {})
        b = buffy_by_id.get(run_id, {})
        pg = p.get("genes") or set()
        bg = b.get("genes") or set()
        all_plasma_genes |= pg
        all_buffy_genes |= bg
        shared = pg & bg
        overlap_rows.append(
            {
                "run_id": run_id,
                "plasma_n": len(pg),
                "buffy_n": len(bg),
                "shared": len(shared),
                "jaccard": _jaccard(pg, bg),
                "plasma_balanced_accuracy": p.get("balanced_accuracy"),
                "buffy_balanced_accuracy": b.get("balanced_accuracy"),
            }
        )

    plasma_freq = _load_gene_frequency(plasma_root, min_frequency)
    buffy_freq = _load_gene_frequency(buffy_root, min_frequency)
    plasma_recurrent = _recurrent_gene_sets(plasma_freq, min_frequency=min_frequency)
    buffy_recurrent = _recurrent_gene_sets(buffy_freq, min_frequency=min_frequency)
    shared_recurrent = plasma_recurrent & buffy_recurrent

    plasma_only = sorted(plasma_recurrent - buffy_recurrent)
    buffy_only = sorted(buffy_recurrent - plasma_recurrent)
    shared_sorted = sorted(shared_recurrent)

    ba_plasma = [r["balanced_accuracy"] for r in plasma_runs if r.get("balanced_accuracy") is not None]
    ba_buffy = [r["balanced_accuracy"] for r in buffy_runs if r.get("balanced_accuracy") is not None]
    mean_ba_plasma = float(sum(ba_plasma) / len(ba_plasma)) if ba_plasma else None
    mean_ba_buffy = float(sum(ba_buffy) / len(ba_buffy)) if ba_buffy else None

    decision = _score_analytes(
        buffy_runs=buffy_runs,
        plasma_runs=plasma_runs,
        buffy_recurrent=buffy_recurrent,
        plasma_recurrent=plasma_recurrent,
        shared_recurrent=shared_recurrent,
        mean_ba_buffy=mean_ba_buffy,
        mean_ba_plasma=mean_ba_plasma,
    )

    summary: Dict[str, Any] = {
        "comparison": comparison,
        "plasma_root": str(plasma_root),
        "buffy_root": str(buffy_root),
        "min_gene_frequency": min_frequency,
        "plasma_mc_runs": len(plasma_runs),
        "buffy_mc_runs": len(buffy_runs),
        "mean_balanced_accuracy": {"plasma": mean_ba_plasma, "buffy": mean_ba_buffy},
        "aggregate_gene_union": {"plasma": len(all_plasma_genes), "buffy": len(all_buffy_genes)},
        "aggregate_jaccard": _jaccard(all_plasma_genes, all_buffy_genes),
        "recurrent_genes": {
            "plasma": len(plasma_recurrent),
            "buffy": len(buffy_recurrent),
            "shared": len(shared_recurrent),
            "jaccard": _jaccard(plasma_recurrent, buffy_recurrent),
        },
        "plasma_gene_frequency_n_runs_max": int(plasma_freq["n_runs"].max()) if not plasma_freq.empty and "n_runs" in plasma_freq.columns else None,
        "buffy_gene_frequency_n_runs_max": int(buffy_freq["n_runs"].max()) if not buffy_freq.empty and "n_runs" in buffy_freq.columns else None,
        "decision": decision,
    }

    return {
        "summary": summary,
        "overlap_by_run": overlap_rows,
        "shared_recurrent_genes": shared_sorted,
        "plasma_only_recurrent": plasma_only,
        "buffy_only_recurrent": buffy_only,
        "decision_scores": decision,
    }


def write_outputs(result: Dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mc_gene_fc_summary.json").write_text(
        json.dumps(result["summary"], indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame(result["overlap_by_run"]).to_csv(out_dir / "mc_gene_overlap_by_run.csv", index=False)
    pd.DataFrame({"gene_name": result["shared_recurrent_genes"]}).to_csv(
        out_dir / "mc_gene_recurrent_shared.csv", index=False
    )
    rows = []
    for g in result["plasma_only_recurrent"]:
        rows.append({"gene_name": g, "analyte": "cfdna"})
    for g in result["buffy_only_recurrent"]:
        rows.append({"gene_name": g, "analyte": "buffy_coat"})
    pd.DataFrame(rows).to_csv(out_dir / "mc_gene_analyte_specific.csv", index=False)
    (out_dir / "mc_gene_decision_scores.json").write_text(
        json.dumps(result["decision_scores"], indent=2) + "\n", encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plasma-root", type=Path, required=True)
    parser.add_argument("--buffy-root", type=Path, required=True)
    parser.add_argument("--comparison", default="all/PCa")
    parser.add_argument("--min-frequency", type=float, default=0.7)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = compare_mc_gene_fc(
        args.plasma_root,
        args.buffy_root,
        min_frequency=args.min_frequency,
        comparison=args.comparison,
    )
    write_outputs(result, args.out)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
