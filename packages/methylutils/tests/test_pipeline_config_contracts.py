"""Regression tests for canonical project-config behavior."""

import json

import pytest

from methyl_utils.pipeline_config import load_project


def test_project_config_normalizes_comparisons_and_predictor_alias(tmp_path):
    config_path = tmp_path / "project.json"
    config_path.write_text(
        json.dumps(
            {
                "project_name": "Contract Test",
                "output_base": "/work",
                "samples_base_path": "/samples",
                "controls": {
                    "label": "controls",
                    "groups": [{"label": "healthy", "sample_paths": ["ctrl_a", "ctrl_b"]}],
                },
                "diseases": {
                    "label": "diseases",
                    "groups": [{"label": "pca", "sample_paths": ["pca_a", "pca_b"]}],
                },
                "comparisons": [{"control_group": "healthy", "disease_group": "pca"}],
                "step_config": {
                    "validator": {"debug": True},
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.warns(DeprecationWarning, match="step_config.validator"):
        project = load_project(str(config_path))

    comparison = project.get_comparisons()[0]
    assert comparison.control_group == "healthy"
    assert comparison.disease_group == "pca"
    assert comparison.comparison_label == "pca"

    assert project.get_step_config("predictor")["debug"] is True

    resolved = project.get_group_sample_paths_by_label("healthy")
    assert resolved == ["/samples/ctrl_a", "/samples/ctrl_b"]


def test_sample_list_csv_resolves_from_samples_base_parent(tmp_path, monkeypatch):
    root = tmp_path / "work"
    data_dir = root / "data"
    configs_dir = root / "configs"
    data_dir.mkdir(parents=True)
    configs_dir.mkdir(parents=True)
    (configs_dir / "healthy.csv").write_text("sample\nA001\nA002\n", encoding="utf-8")

    config_path = tmp_path / "project.json"
    config_path.write_text(
        json.dumps(
            {
                "project_name": "Contract Test",
                "output_base": str(root / "out"),
                "samples_base_path": str(data_dir),
                "controls": {
                    "label": "controls",
                    "groups": [{"label": "healthy", "sample_paths": ["configs/healthy.csv"]}],
                },
                "diseases": {
                    "label": "diseases",
                    "groups": [{"label": "pca", "sample_paths": ["P001"]}],
                },
                "comparisons": [{"control_group": "healthy", "disease_group": "pca"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    project = load_project(str(config_path))
    resolved = project.get_group_sample_paths_by_label("healthy")
    assert resolved == [str(data_dir / "A001"), str(data_dir / "A002")]


