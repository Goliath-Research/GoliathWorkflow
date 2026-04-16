from __future__ import annotations

import pytest

from methyl_validation.config import MonteCarloConfig


def _base_payload() -> dict:
    return {
        "samples_base_path": "/tmp",
        "cohorts": [{"label": "healthy", "csv": "h.csv"}, {"label": "disease", "csv": "d.csv"}],
        "train_fraction": 0.8,
        "n_iterations": 1,
        "base_project": "/tmp/project.json",
        "output_base": "/tmp",
        "model_backend": "tabular_sklearn",
    }


def test_tabular_methods_discriminated_union_parses():
    payload = _base_payload()
    payload["tabular_methods"] = [
        {"method": "random_forest", "params": {"n_estimators": 123}},
        {"method": "logistic_regression", "params": {"max_iter": 222, "c": 0.5}},
    ]
    cfg = MonteCarloConfig.model_validate(payload)
    assert len(cfg.tabular_methods or []) == 2
    assert cfg.tabular_methods[0].method == "random_forest"
    assert cfg.tabular_methods[0].params.n_estimators == 123
    assert cfg.tabular_methods[1].method == "logistic_regression"
    assert cfg.tabular_methods[1].params.max_iter == 222


def test_tabular_methods_synthesized_from_legacy_model_type():
    payload = _base_payload()
    payload["tabular_model_type"] = "hist_gradient_boosting"
    cfg = MonteCarloConfig.model_validate(payload)
    assert cfg.tabular_methods is not None
    assert len(cfg.tabular_methods) == 1
    assert cfg.tabular_methods[0].method == "hist_gradient_boosting"


def test_tabular_method_selection_metric_is_validated():
    payload = _base_payload()
    payload["tabular_method_selection_metric"] = "roc_auc"
    with pytest.raises(ValueError, match="tabular_method_selection_metric"):
        MonteCarloConfig.model_validate(payload)
