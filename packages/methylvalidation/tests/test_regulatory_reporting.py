from __future__ import annotations

import json

import pytest

from methyl_validation.clinical_performance import write_clinical_performance_report
from methyl_validation.config import MonteCarloConfig, RegulatoryLifecycleConfig
from methyl_validation.locked_model_spec import write_locked_model_spec


def _base_config_dict(tmp_path) -> dict:
    base_project = tmp_path / "project.json"
    base_project.write_text("{}", encoding="utf-8")
    return {
        "samples_base_path": str(tmp_path),
        "cohorts": [{"label": "control", "csv": "c.csv"}, {"label": "disease", "csv": "d.csv"}],
        "train_fraction": 0.8,
        "n_iterations": 2,
        "base_project": str(base_project),
        "output_base": str(tmp_path / "out"),
    }


def test_regulatory_lifecycle_blocks_claims_before_pivotal() -> None:
    with pytest.raises(ValueError):
        RegulatoryLifecycleConfig(
            stage="feasibility",
            allow_clinical_performance_claims=True,
        )


def test_clinical_performance_report_writes_ci_and_gate(tmp_path) -> None:
    cfg = MonteCarloConfig.model_validate(
        {
            **_base_config_dict(tmp_path),
            "min_sensitivity_lcb": 0.2,
        }
    )
    out_dir = tmp_path / "predictor"
    metrics = {"confusion_matrix": [[30, 5], [4, 31]], "balanced_accuracy": 0.87}
    result = write_clinical_performance_report(
        output_dir=out_dir,
        metrics=metrics,
        config=cfg,
        source="unit-test",
    )
    assert (out_dir / "clinical_performance_report.json").is_file()
    assert (out_dir / "clinical_performance_report.md").is_file()
    assert result["payload"]["confidence_intervals"]["available"] is True
    assert result["payload"]["acceptance_gates"]["configured"] is True


def test_locked_model_spec_writes_hashes(tmp_path) -> None:
    prod = tmp_path / "production"
    prod.mkdir(parents=True, exist_ok=True)
    (prod / "project.json").write_text(
        json.dumps(
            {
                "step_config": {
                    "validation": {"regulatory": {"stage": "model_freeze"}},
                    "model_bundle": {},
                }
            }
        ),
        encoding="utf-8",
    )
    stable = prod / "stable_dmps_genomewide.csv"
    stable.write_text("chromosome,position\nchr1,1\n", encoding="utf-8")
    result = write_locked_model_spec(
        production_dir=prod,
        source_event="unit-test",
        config=None,
    )
    assert (prod / "locked_model_spec.json").is_file()
    assert (prod / "locked_model_spec.md").is_file()
    assert result["payload"]["artifacts"]["fixed_dmp_panel"]["sha256"] is not None

