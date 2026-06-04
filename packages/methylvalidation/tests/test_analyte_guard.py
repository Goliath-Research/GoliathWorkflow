"""Tests for training analyte consistency checks."""

import json
from pathlib import Path

from methyl_validation.analyte_guard import (
    check_training_analyte_match,
    effective_training_analyte,
    normalize_analyte,
)


def test_normalize_plasma_to_cfdna():
    assert normalize_analyte("plasma") == "cfdna"
    assert normalize_analyte("buffy_coat") == "buffy_coat"


def test_effective_training_analyte_prefers_model_field():
    reg = {"primary_analyte": "cfdna", "model_training_analyte": "buffy_coat"}
    assert effective_training_analyte(reg) == "buffy_coat"


def test_check_training_analyte_mismatch(tmp_path: Path):
    prod = tmp_path / "production"
    prod.mkdir()
    (prod / "locked_model_spec.json").write_text(
        json.dumps({"regulatory": {"model_training_analyte": "buffy_coat"}}),
        encoding="utf-8",
    )
    project = tmp_path / "project.json"
    project.write_text(
        json.dumps(
            {
                "project_name": "t",
                "output_base": str(tmp_path),
                "group1": {"label": "a", "sample_paths": []},
                "group2": {"label": "b", "sample_paths": []},
                "step_config": {
                    "validation": {
                        "regulatory": {
                            "primary_analyte": "cfdna",
                            "model_training_analyte": "cfdna",
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    ok, msg = check_training_analyte_match(
        project_json=project,
        production_dir=prod,
    )
    assert ok is False
    assert "mismatch" in msg
