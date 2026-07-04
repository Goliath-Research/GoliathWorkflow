"""Tests for held-out batch resolution, training exclusion, and prediction reading."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from methyl_validation.holdout_eval import (
    apply_holdout_exclusion_to_project_dict,
    read_predictions_for_bootstrap,
    resolve_holdout_groups,
    _preflight_exclusion,
    write_holdout_manifest,
    HOLDOUT_MANIFEST_NAME,
)


def _write_csv(path: Path, names: list[str]) -> None:
    path.write_text("sample\n" + "\n".join(names) + "\n", encoding="utf-8")


def _binary_project(tmp_path: Path) -> dict:
    base = tmp_path / "samples"
    base.mkdir()
    healthy_csv = tmp_path / "healthy.csv"
    cancer_csv = tmp_path / "cancer.csv"
    _write_csv(healthy_csv, ["H1", "H2", "H3", "H4"])
    _write_csv(cancer_csv, ["C1", "C2", "C3", "C4"])
    return {
        "samples_base_path": str(base),
        "controls": {"groups": [{"label": "all", "sample_paths": [str(healthy_csv)]}]},
        "diseases": {"groups": [{"label": "cancer", "sample_paths": [str(cancer_csv)]}]},
    }


def test_resolve_holdout_groups_binary(tmp_path):
    project = _binary_project(tmp_path)
    base = project["samples_base_path"]
    holdout = [str(Path(base) / "H3"), str(Path(base) / "H4"), str(Path(base) / "C3")]
    resolved = resolve_holdout_groups(project, holdout)
    assert resolved["binary"] is True
    assert sorted(Path(p).name for p in resolved["control_paths"]) == ["H3", "H4"]
    assert sorted(Path(p).name for p in resolved["disease_paths"]) == ["C3"]
    assert resolved["unresolved"] == []


def test_resolve_holdout_reports_unresolved(tmp_path):
    project = _binary_project(tmp_path)
    resolved = resolve_holdout_groups(project, ["/nowhere/UNKNOWN_X"])
    assert resolved["unresolved"] == ["UNKNOWN_X"]


def test_apply_holdout_exclusion_removes_from_cohorts(tmp_path):
    project = _binary_project(tmp_path)
    out = tmp_path / "prod"
    out.mkdir()
    excluded = apply_holdout_exclusion_to_project_dict(project, {"H3", "H4", "C4"}, out)
    assert sorted(excluded) == ["C4", "H3", "H4"]
    # Project now points at filtered CSVs; verify hold-out names are gone.
    healthy_csv = project["controls"]["groups"][0]["sample_paths"][0]
    kept = [ln.strip() for ln in Path(healthy_csv).read_text().splitlines()[1:] if ln.strip()]
    assert kept == ["H1", "H2"]
    cancer_csv = project["diseases"]["groups"][0]["sample_paths"][0]
    kept_c = [ln.strip() for ln in Path(cancer_csv).read_text().splitlines()[1:] if ln.strip()]
    assert kept_c == ["C1", "C2", "C3"]


def test_preflight_exclusion_pass_and_fail(tmp_path):
    manifest_dir = tmp_path / "production"
    manifest_dir.mkdir()
    write_holdout_manifest(
        manifest_dir, partition="locked_test", holdout_paths=["/x/H3", "/x/H4"], excluded=["H3", "H4"]
    )
    ok, msg = _preflight_exclusion(manifest_dir / HOLDOUT_MANIFEST_NAME, {"H3", "H4"})
    assert ok, msg
    ok2, msg2 = _preflight_exclusion(manifest_dir / HOLDOUT_MANIFEST_NAME, {"H3", "H4", "H5"})
    assert not ok2
    assert "H5" in msg2


def test_preflight_missing_manifest(tmp_path):
    ok, msg = _preflight_exclusion(tmp_path / "nope.json", {"H1"})
    assert not ok
    assert "Re-run" in msg


def test_read_predictions_for_bootstrap(tmp_path):
    csv_path = tmp_path / "predictions.csv"
    pd.DataFrame(
        {
            "sample": ["H1", "C1"],
            "expected_class": [0, 1],
            "prediction": [0, 1],
            "prob_class0": [0.8, 0.3],
            "prob_class1": [0.2, 0.7],
        }
    ).to_csv(csv_path, index=False)
    arrays = read_predictions_for_bootstrap(csv_path)
    assert arrays["y_true"].tolist() == [0, 1]
    assert arrays["y_pred"].tolist() == [0, 1]
    assert arrays["y_proba"].shape == (2, 2)


def test_read_predictions_requires_labels(tmp_path):
    csv_path = tmp_path / "predictions.csv"
    pd.DataFrame({"sample": ["H1"], "prediction": [0]}).to_csv(csv_path, index=False)
    with pytest.raises(ValueError):
        read_predictions_for_bootstrap(csv_path)
