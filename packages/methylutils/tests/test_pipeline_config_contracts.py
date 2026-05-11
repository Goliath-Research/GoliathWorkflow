"""Regression tests for canonical project-config behavior."""

import json

import pytest

from methyl_utils.pipeline_config import load_project


def test_derive_panel_and_ordered_comparison_labels_from_comparisons(tmp_path):
    list_dir = tmp_path / "lists"
    list_dir.mkdir()
    for name in ("h.csv", "p1.csv", "p2.csv", "p3.csv"):
        (list_dir / name).write_text("sample\ns1\n", encoding="utf-8")

    config_path = tmp_path / "project.json"
    config_path.write_text(
        json.dumps(
            {
                "project_name": "PanelDerive",
                "output_base": str((tmp_path / "out").resolve()),
                "samples_base_path": str(tmp_path.resolve()),
                "controls": {
                    "label": "healthy",
                    "groups": [{"label": "all", "sample_paths": [str((list_dir / "h.csv").resolve())]}],
                },
                "diseases": {
                    "label": "cancer",
                    "groups": [
                        {
                            "label": "pca",
                            "stages": [
                                {"label": "pca1", "sample_paths": [str((list_dir / "p1.csv").resolve())]},
                                {"label": "pca2", "sample_paths": [str((list_dir / "p2.csv").resolve())]},
                                {"label": "pca3", "sample_paths": [str((list_dir / "p3.csv").resolve())]},
                            ],
                        }
                    ],
                },
                "comparisons": "control_vs_each_disease",
            }
        ),
        encoding="utf-8",
    )
    project = load_project(str(config_path))
    assert project.get_ordered_comparison_labels() == ["pca_pca1", "pca_pca2", "pca_pca3"]
    panel = project.derive_panel_spec_from_comparisons()
    assert panel is not None
    assert panel["primary_family"] == "pca"
    assert panel["families"] == {"pca": ["pca_pca1", "pca_pca2", "pca_pca3"]}
    assert panel["indeterminate_delta"] == 0.25


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


