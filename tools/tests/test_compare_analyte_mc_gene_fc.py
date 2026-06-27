"""Tests for compare_analyte_mc_gene_fc."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from compare_analyte_mc_gene_fc import _score_analytes, compare_mc_gene_fc, write_outputs


def _write_run(root: Path, run_id: str, genes: list[str], ba: float = 1.0) -> None:
    gs = root / "monte_carlo_runs" / run_id / "gene_stability"
    gs.mkdir(parents=True)
    (gs / "gene_featurecuts_metrics.json").write_text(
        json.dumps({"balanced_accuracy": ba, "selected_k": len(genes)}),
        encoding="utf-8",
    )
    pd.DataFrame({"gene_name": genes}).to_csv(gs / "genes-classifier.csv", index=False)


def _write_freq(root: Path, rows: list[dict]) -> None:
    stab = root / "monte_carlo_runs" / "stability"
    stab.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(stab / "gene_frequency.csv", index=False)


def test_compare_mc_gene_fc_overlap(tmp_path: Path) -> None:
    plasma = tmp_path / "plasma"
    buffy = tmp_path / "buffy"
    _write_run(plasma, "run_0001", ["G1", "G2", "G3"])
    _write_run(buffy, "run_0001", ["G2", "G3", "G4"])
    _write_freq(
        plasma,
        [{"gene_name": "G2", "frequency": 1.0, "count": 1, "n_runs": 1}],
    )
    _write_freq(
        buffy,
        [{"gene_name": "G2", "frequency": 1.0, "count": 1, "n_runs": 1}],
    )

    result = compare_mc_gene_fc(plasma, buffy, min_frequency=0.7)
    assert result["overlap_by_run"][0]["shared"] == 2
    assert "G2" in result["shared_recurrent_genes"]
    assert result["summary"]["decision"]["recommended_analyte"] in {"buffy_coat", "cfdna", "tie"}

    out = tmp_path / "out"
    write_outputs(result, out)
    assert (out / "mc_gene_fc_summary.json").is_file()
    assert (out / "mc_gene_overlap_by_run.csv").is_file()


def test_cross_analyte_concordance_differs_per_analyte() -> None:
    """Per-analyte concordance must differ so the 30% weight is not cancelled in weighted_total."""
    buffy_recurrent = {"G1", "G2", "G3", "G4"}
    plasma_recurrent = {"G1", "G2"}
    shared = buffy_recurrent & plasma_recurrent

    decision = _score_analytes(
        buffy_runs=[{"run_id": "run_0001"}],
        plasma_runs=[{"run_id": "run_0001"}],
        buffy_recurrent=buffy_recurrent,
        plasma_recurrent=plasma_recurrent,
        shared_recurrent=shared,
        mean_ba_buffy=1.0,
        mean_ba_plasma=1.0,
    )

    buffy_conc = decision["scores"]["buffy_coat"]["cross_analyte_concordance"]
    plasma_conc = decision["scores"]["cfdna"]["cross_analyte_concordance"]
    assert buffy_conc != plasma_conc
    assert plasma_conc > buffy_conc  # 2/2 shared vs 2/4 shared

    weights = decision["weights"]
    buffy_conc_contrib = weights["cross_analyte_concordance"] * buffy_conc
    plasma_conc_contrib = weights["cross_analyte_concordance"] * plasma_conc
    assert buffy_conc_contrib != plasma_conc_contrib

    # Pair-level Jaccard still reported separately from per-analyte scores
    assert decision["recurrent_jaccard"] == 0.5  # |shared| / |union| = 2/4
