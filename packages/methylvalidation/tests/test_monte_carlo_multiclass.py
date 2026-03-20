"""Monte Carlo config, layout inference, predictor policy, and multiclass split."""

import json
from pathlib import Path

import pytest

from methyl_validation.config import MonteCarloConfig
from methyl_validation.predictor_policy import assert_monte_carlo_predictor_allowed, monte_carlo_rejects_blind_predictor
from methyl_validation.project_gen import infer_monte_carlo_layout
from methyl_validation.split import stratified_split_multiclass


def test_stratified_split_multiclass_three_classes():
    cohorts = [
        ("a", [f"/x/a{i}" for i in range(6)]),
        ("b", [f"/x/b{i}" for i in range(6)]),
        ("c", [f"/x/c{i}" for i in range(6)]),
    ]
    train_m, val_m = stratified_split_multiclass(cohorts, train_fraction=0.5, seed=99)
    assert len(train_m["a"]) == 3 and len(val_m["a"]) == 3
    assert sorted(train_m["a"] + val_m["a"]) == sorted(cohorts[0][1])


def test_stratified_split_multiclass_unique_labels_required():
    with pytest.raises(ValueError, match="unique"):
        stratified_split_multiclass(
            [("a", ["/1"]), ("a", ["/2"])],
            train_fraction=0.5,
            seed=1,
        )


def test_monte_carlo_config_legacy_healthy_disease():
    c = MonteCarloConfig.model_validate(
        {
            "samples_base_path": "/tmp/s",
            "healthy_csv": "h.csv",
            "disease_csv": "d.csv",
            "train_fraction": 0.8,
            "n_iterations": 2,
            "base_project": "p.json",
            "output_base": "/tmp/out",
        }
    )
    assert len(c.cohorts) == 2
    assert c.cohorts[0].label == "healthy"
    assert c.cohorts[1].csv == "d.csv"


def test_monte_carlo_config_explicit_cohorts():
    c = MonteCarloConfig.model_validate(
        {
            "samples_base_path": "/tmp/s",
            "cohorts": [
                {"label": "g0", "csv": "a.csv"},
                {"label": "g1", "csv": "b.csv"},
                {"label": "g2", "csv": "c.csv"},
            ],
            "train_fraction": 0.8,
            "n_iterations": 1,
            "base_project": "p.json",
            "output_base": "/tmp/out",
        }
    )
    assert [x.label for x in c.cohorts] == ["g0", "g1", "g2"]


def test_infer_monte_carlo_layout_binary(tmp_path: Path):
    p = tmp_path / "proj.json"
    p.write_text(
        json.dumps(
            {
                "project_name": "x",
                "output_base": "/o",
                "samples_base_path": "/s",
                "controls": {"label": "c", "groups": [{"label": "h", "sample_paths": []}]},
                "diseases": {"label": "d", "groups": [{"label": "t", "sample_paths": []}]},
                "comparisons": [{"control_group": "h", "disease_group": "t"}],
            }
        ),
        encoding="utf-8",
    )
    assert infer_monte_carlo_layout(p, 2) == "binary"


def test_infer_monte_carlo_layout_hierarchical_multiclass(tmp_path: Path):
    """K>=3 resolved groups under controls/diseases → hierarchical_multiclass layout."""
    paths = []
    for name in ("a.csv", "b.csv", "c.csv"):
        fp = tmp_path / name
        fp.write_text("sample\ns1\n", encoding="utf-8")
        paths.append(str(fp.resolve()))
    p = tmp_path / "proj.json"
    p.write_text(
        json.dumps(
            {
                "project_name": "x",
                "output_base": str((tmp_path / "out").resolve()),
                "samples_base_path": str(tmp_path.resolve()),
                "controls": {
                    "label": "c",
                    "groups": [
                        {"label": "h1", "sample_paths": [paths[0]]},
                        {"label": "h2", "sample_paths": [paths[1]]},
                    ],
                },
                "diseases": {
                    "label": "d",
                    "groups": [{"label": "d1", "sample_paths": [paths[2]]}],
                },
                "comparisons": "all_pairs",
            }
        ),
        encoding="utf-8",
    )
    assert infer_monte_carlo_layout(p, 3) == "hierarchical_multiclass"


def test_infer_monte_carlo_layout_multiclass(tmp_path: Path):
    p = tmp_path / "proj.json"
    p.write_text(
        json.dumps(
            {
                "groups": [
                    {"label": "c0", "sample_paths": []},
                    {"label": "c1", "sample_paths": []},
                    {"label": "c2", "sample_paths": []},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert infer_monte_carlo_layout(p, 3) == "multiclass"


def test_predictor_policy_blind():
    assert monte_carlo_rejects_blind_predictor({"blind": {"groups": [{"label": "x"}]}})
    assert not monte_carlo_rejects_blind_predictor({})
    with pytest.raises(ValueError, match="blind"):
        assert_monte_carlo_predictor_allowed({"blind": {"groups": [{"label": "x"}]}})
