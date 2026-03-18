"""Regression tests for canonical project-config behavior."""

import json

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

    project = load_project(str(config_path))

    comparison = project.get_comparisons()[0]
    assert comparison.control_group == "healthy"
    assert comparison.disease_group == "pca"
    assert comparison.comparison_label == "pca"

    assert project.get_step_config("predictor")["debug"] is True

    resolved = project.get_group_sample_paths_by_label("healthy")
    assert resolved == ["/samples/ctrl_a", "/samples/ctrl_b"]
