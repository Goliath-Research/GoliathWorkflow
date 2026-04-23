from __future__ import annotations

import json
from pathlib import Path

from methyl_validation.config import MonteCarloConfig
from methyl_validation.trainer_api import build_model_backend_steps


def _base_config(tmp_path: Path, enabled: bool) -> MonteCarloConfig:
    return MonteCarloConfig.model_validate(
        {
            "samples_base_path": "/tmp",
            "cohorts": [{"label": "healthy", "csv": "h.csv"}, {"label": "disease", "csv": "d.csv"}],
            "train_fraction": 0.8,
            "n_iterations": 1,
            "base_project": str(tmp_path / "project.json"),
            "output_base": str(tmp_path),
            "model_backend": "ecdf",
            "ecdf_second_stage_enabled": enabled,
            "observed_feature_include_dmr": True,
            "observed_feature_include_gene": True,
            "observed_feature_max_dmrs": 7,
            "observed_feature_max_genes": 9,
        }
    )


def test_build_model_backend_steps_ecdf_includes_second_stage(tmp_path: Path, monkeypatch):
    called = {"n": 0, "kwargs": None}
    tm_called = {"n": 0, "args": None}

    def _fake_second_stage(**kwargs):
        called["n"] += 1
        called["kwargs"] = kwargs
        return {"ok": True, "predictor_output_dir": str(kwargs["predictor_output_dir"])}

    def _fake_training_metrics(project_json: Path, classifier_output_dir: Path):
        tm_called["n"] += 1
        tm_called["args"] = (project_json, classifier_output_dir)
        return True, str(classifier_output_dir / "training_metrics.json")

    monkeypatch.setattr("methyl_validation.ecdf_second_stage.train_and_apply_ecdf_second_stage", _fake_second_stage)
    monkeypatch.setattr("methyl_validation.trainer_api._write_ecdf_training_metrics", _fake_training_metrics)
    steps = build_model_backend_steps(
        project_json=tmp_path / "project.json",
        predictor_output_dir=tmp_path / "predictors",
        config=_base_config(tmp_path, enabled=True),
        per_cancer_group=False,
        run_classifier_fn=lambda _p, _g: (0, "classifier ok", ""),
        run_predictor_fn=lambda _p, _o: (0, "predictor ok", ""),
    )
    assert [name for name, _fn in steps] == ["methyl-classifier", "methyl-predictor", "ecdf-second-stage"]
    rc, out, err = steps[-1][1]()
    assert rc == 0
    assert err == ""
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["training_metrics_saved"] is True
    assert called["n"] == 1
    assert tm_called["n"] == 1
    assert called["kwargs"]["max_dmr_features"] == 7
    assert called["kwargs"]["max_gene_features"] == 9


def test_build_model_backend_steps_ecdf_second_stage_disabled(tmp_path: Path, monkeypatch):
    tm_called = {"n": 0}

    def _fake_training_metrics(project_json: Path, classifier_output_dir: Path):
        tm_called["n"] += 1
        return True, str(classifier_output_dir / "training_metrics.json")

    monkeypatch.setattr("methyl_validation.trainer_api._write_ecdf_training_metrics", _fake_training_metrics)
    steps = build_model_backend_steps(
        project_json=tmp_path / "project.json",
        predictor_output_dir=tmp_path / "predictors",
        config=_base_config(tmp_path, enabled=False),
        per_cancer_group=False,
        run_classifier_fn=lambda _p, _g: (0, "classifier ok", ""),
        run_predictor_fn=lambda _p, _o: (0, "predictor ok", ""),
    )
    rc, out, err = steps[-1][1]()
    assert rc == 0
    assert "disabled" in out.lower()
    assert "training metrics" in out.lower()
    assert tm_called["n"] == 1
    assert err == ""
