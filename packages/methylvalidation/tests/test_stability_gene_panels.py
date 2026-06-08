from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from methyl_validation.stability import (
    compute_gene_stability,
    evaluate_gene_stability_convergence,
    load_classifier_genes,
    run_stability_analysis,
    write_stable_gene_panel,
)


def _write_classifier_genes(run_dir: Path, genes: list[str]) -> None:
    out = run_dir / "gene_stability"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "gene_name": genes,
            "gene_importance": [0.9, 0.8][: len(genes)],
            "mean_effect_size": [0.3, 0.2][: len(genes)],
        }
    ).to_csv(out / "genes-classifier.csv", index=False)


def test_load_classifier_genes_reads_gene_stability_export(tmp_path: Path):
    run_dir = tmp_path / "run_0001"
    _write_classifier_genes(run_dir, ["BRCA1", "TP53"])
    df = load_classifier_genes(run_dir)
    assert df is not None
    assert set(df["gene_name"].astype(str)) == {"BRCA1", "TP53"}


def test_compute_gene_stability_counts_classifier_panels(tmp_path: Path):
    mc_root = tmp_path / "monte_carlo_runs"
    for idx, genes in enumerate([["BRCA1", "TP53"], ["BRCA1"], ["TP53"]], start=1):
        run_dir = mc_root / f"run_{idx:04d}"
        _write_classifier_genes(run_dir, genes)
        det = run_dir / "detections" / "chr1" / "cmp"
        det.mkdir(parents=True)
        (det / "results-cmp.json").write_text(
            '{"optimization_validation":{"performance":{"balanced_accuracy":0.95}}}',
            encoding="utf-8",
        )

    df, summary = compute_gene_stability(
        mc_root,
        min_frequency=0.5,
        min_balanced_accuracy=0.9,
        prefer_classifier_gene_panels=True,
    )
    assert summary["n_runs_analyzed"] == 3
    assert summary["prefer_classifier_gene_panels"] is True
    brca = df[df["gene_name"] == "BRCA1"].iloc[0]
    assert brca["frequency"] == pytest.approx(2 / 3)


def _write_enricher_genes(run_dir: Path, genes: list[str]) -> None:
    enricher_dir = run_dir / "enricher" / "default" / "cmp"
    enricher_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"gene_name": genes}).to_csv(
        enricher_dir / "all-gene_name-combined.csv",
        index=False,
    )


def test_compute_gene_stability_enricher_without_metric_columns(tmp_path: Path):
    mc_root = tmp_path / "monte_carlo_runs"
    for idx, genes in enumerate([["BRCA1"], ["BRCA1", "TP53"]], start=1):
        run_dir = mc_root / f"run_{idx:04d}"
        _write_enricher_genes(run_dir, genes)

    df, summary = compute_gene_stability(mc_root, min_frequency=0.5)
    assert summary["n_runs_analyzed"] == 2
    assert set(df["gene_name"].astype(str)) == {"BRCA1", "TP53"}
    assert "gene_importance" not in df.columns
    assert "mean_effect_size" not in df.columns


def test_write_stable_gene_panel_and_stability_analysis(tmp_path: Path):
    mc_root = tmp_path / "monte_carlo_runs"
    for idx in range(1, 4):
        run_dir = mc_root / f"run_{idx:04d}"
        _write_classifier_genes(run_dir, ["BRCA1", "TP53"])
        det = run_dir / "detections" / "chr1" / "cmp"
        det.mkdir(parents=True)
        pd.DataFrame(
            {
                "chromosome": ["1"],
                "position": [100],
                "context": ["CG"],
                "effect_size": [0.5],
            }
        ).to_csv(det / "dmps-cmp-classifier.csv", index=False)

    summary = run_stability_analysis(
        mc_root,
        dmp_min_freq=0.5,
        gene_min_freq=0.5,
        prefer_classifier_panel_dmps=True,
        prefer_classifier_gene_panels=True,
    )
    stable_gene_csv = Path(summary["stable_gene_csv"])
    assert stable_gene_csv.is_file()
    stable = pd.read_csv(stable_gene_csv)
    assert set(stable["gene_name"].astype(str)) == {"BRCA1", "TP53"}
    assert (mc_root / "stability" / "gene_frequency.csv").is_file()


def test_evaluate_gene_stability_convergence_detects_converged_panel(tmp_path: Path):
    mc_root = tmp_path / "monte_carlo_runs"
    for idx in range(1, 7):
        _write_classifier_genes(mc_root / f"run_{idx:04d}", ["BRCA1", "TP53"])

    result = evaluate_gene_stability_convergence(
        mc_root,
        min_frequency=0.8,
        prefer_classifier_gene_panels=True,
        min_iterations=5,
        convergence_window=2,
        convergence_jaccard=0.99,
        convergence_max_size_delta=0.0,
    )
    assert result["axis"] == "gene"
    assert result["eligible_for_check"] is True
    assert result["converged_checkpoint"] is True
    assert result["jaccard"] == 1.0
    assert result["relative_size_delta"] == 0.0


def test_evaluate_gene_stability_convergence_detects_drift(tmp_path: Path):
    mc_root = tmp_path / "monte_carlo_runs"
    # First runs are stable on BRCA1/TP53; later runs introduce new genes so the
    # current stable panel diverges from the lagged panel.
    panels = [
        ["BRCA1", "TP53"],
        ["BRCA1", "TP53"],
        ["BRCA1", "TP53"],
        ["EGFR", "KRAS"],
        ["EGFR", "KRAS"],
        ["EGFR", "KRAS"],
    ]
    for idx, genes in enumerate(panels, start=1):
        _write_classifier_genes(mc_root / f"run_{idx:04d}", genes)

    result = evaluate_gene_stability_convergence(
        mc_root,
        min_frequency=0.9,
        prefer_classifier_gene_panels=True,
        min_iterations=5,
        convergence_window=3,
        convergence_jaccard=0.99,
        convergence_max_size_delta=0.0,
    )
    assert result["axis"] == "gene"
    assert result["eligible_for_check"] is True
    assert result["converged_checkpoint"] is False
    assert result["jaccard"] < 0.99


def test_evaluate_gene_stability_convergence_reports_insufficient_runs(tmp_path: Path):
    mc_root = tmp_path / "monte_carlo_runs"
    for idx in range(1, 4):
        _write_classifier_genes(mc_root / f"run_{idx:04d}", ["BRCA1", "TP53"])

    result = evaluate_gene_stability_convergence(
        mc_root,
        min_frequency=0.8,
        prefer_classifier_gene_panels=True,
        min_iterations=5,
        convergence_window=2,
    )
    assert result["axis"] == "gene"
    assert result["eligible_for_check"] is False
    assert result["converged_checkpoint"] is False
    assert result["reason"] == "insufficient_qualifying_runs"
