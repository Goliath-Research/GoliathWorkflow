"""Covariate preprocessor safety: exclude label/diagnostic columns on auto-infer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from methyl_validation.covariate_preprocessor import fit_covariates


def _cell_fractions_csv(path: Path) -> Path:
    rows = []
    for i, group in enumerate(["all"] * 4 + ["PCa"] * 4):
        rows.append(
            {
                "sample_id": f"S{i}",
                "group": group,
                "CD8T": 0.05 + 0.01 * i,
                "CD4T": 0.15,
                "NK": 0.05,
                "Bcell": 0.05,
                "Mono": 0.10,
                "Neu": 0.60 - 0.01 * i,
                "n_markers_observed": 400 + i,
                "marker_fraction": 0.95,
                "qp_status": "ok",
            }
        )
    path.write_text(pd.DataFrame(rows).to_csv(index=False), encoding="utf-8")
    return path


def test_auto_infer_excludes_group_and_deconv_diagnostics(tmp_path: Path):
    cov = _cell_fractions_csv(tmp_path / "cell_fractions.csv")
    sample_ids = [f"S{i}" for i in range(8)]
    X, prep, report = fit_covariates(
        str(cov),
        sample_ids,
        covariate_id_column="sample_id",
        strict_join=True,
    )
    assert X is not None and prep is not None
    assert prep.numeric_columns == ["CD8T", "CD4T", "NK", "Bcell", "Mono", "Neu"]
    assert prep.categorical_columns == []
    assert "group" not in (prep.output_columns or [])
    assert "qp_status" not in "".join(prep.output_columns or [])
    assert set(report["auto_excluded_columns"]) >= {
        "group",
        "qp_status",
        "n_markers_observed",
        "marker_fraction",
    }
    assert X.shape == (8, 6)


def test_explicit_numeric_can_include_marker_fraction(tmp_path: Path):
    cov = _cell_fractions_csv(tmp_path / "cell_fractions.csv")
    sample_ids = [f"S{i}" for i in range(8)]
    X, prep, report = fit_covariates(
        str(cov),
        sample_ids,
        covariate_id_column="sample_id",
        strict_join=True,
        numeric_columns=["CD8T", "Neu", "marker_fraction"],
    )
    assert prep is not None
    assert prep.numeric_columns == ["CD8T", "Neu", "marker_fraction"]
    assert report["auto_excluded_columns"] == []
    assert X is not None and X.shape == (8, 3)
