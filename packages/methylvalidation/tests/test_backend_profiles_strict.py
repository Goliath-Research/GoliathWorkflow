from __future__ import annotations

import pytest

from methyl_validation.cli import _resolve_model_mc_backends
from methyl_validation.config import MonteCarloConfig
from methyl_validation.mc_config_load import _update_backend_params
from methyl_validation.utils.migrate_backend_config import _migrate_validation_section


def _base_payload() -> dict:
    return {
        "samples_base_path": "/tmp",
        "cohorts": [{"label": "healthy", "csv": "h.csv"}, {"label": "disease", "csv": "d.csv"}],
        "train_fraction": 0.8,
        "n_iterations": 2,
        "base_project": "/tmp/project.json",
        "output_base": "/tmp",
        "backend_profiles": {
            "ecdf": {"enabled": False, "params": {}},
            "tabular_sklearn": {"enabled": True, "params": {}},
            "generative_hybrid": {"enabled": True, "params": {}},
        },
    }


def test_model_mc_all_uses_only_enabled_profiles():
    cfg = MonteCarloConfig.model_validate(_base_payload())
    backends = _resolve_model_mc_backends(cfg, run_all=True)
    assert backends == ["tabular_sklearn", "generative_hybrid"]


def test_model_mc_all_fails_when_no_enabled_profiles():
    payload = _base_payload()
    payload["backend_profiles"]["tabular_sklearn"]["enabled"] = False
    payload["backend_profiles"]["generative_hybrid"]["enabled"] = False
    with pytest.raises(ValueError, match="At least one backend profile must have enabled=true"):
        MonteCarloConfig.model_validate(payload)


def test_migration_moves_legacy_keys_into_backend_profiles():
    legacy = {
        "model_backend": "generative_hybrid",
        "tabular_max_dmps": 7000,
        "generative_latent_dim": 24,
        "generative_epochs": 99,
    }
    migrated, summary = _migrate_validation_section(legacy)
    assert "model_backend" not in migrated
    assert migrated["backend_profiles"]["generative_hybrid"]["enabled"] is True
    assert migrated["backend_profiles"]["ecdf"]["enabled"] is False
    assert migrated["backend_profiles"]["tabular_sklearn"]["params"]["tabular_max_dmps"] == 7000
    assert migrated["backend_profiles"]["generative_hybrid"]["params"]["generative_latent_dim"] == 24
    assert summary["active_backend"] == "generative_hybrid"


def test_with_backend_selection_resyncs_runtime_fields():
    payload = _base_payload()
    payload["backend_profiles"]["ecdf"]["enabled"] = True
    payload["backend_profiles"]["generative_hybrid"]["enabled"] = False
    payload["backend_profiles"]["ecdf"]["params"] = {
        "feature_mode": "raw_dmp",
        "tabular_max_dmps": 5000,
    }
    payload["backend_profiles"]["tabular_sklearn"]["params"] = {
        "feature_mode": "observed_hybrid",
        "tabular_max_dmps": 7777,
    }
    cfg = MonteCarloConfig.model_validate(payload)
    switched = cfg.with_backend_selection("tabular_sklearn")
    assert switched.model_backend == "tabular_sklearn"
    assert switched.feature_mode == "observed_hybrid"
    assert switched.tabular_max_dmps == 7777


def test_update_backend_params_resyncs_runtime_fields():
    payload = _base_payload()
    payload["backend_profiles"]["ecdf"]["enabled"] = False
    payload["backend_profiles"]["tabular_sklearn"]["enabled"] = False
    payload["backend_profiles"]["generative_hybrid"]["enabled"] = True
    cfg = MonteCarloConfig.model_validate(payload)
    updated = _update_backend_params(
        cfg,
        "generative_hybrid",
        {"generative_latent_dim": 31, "covariates_path": "/tmp/covariates.csv"},
    )
    assert updated.backend_profiles.generative_hybrid.params.generative_latent_dim == 31
    assert updated.generative_latent_dim == 31
    assert updated.covariates_path == "/tmp/covariates.csv"


def test_gene_feature_loading_is_shared_and_migrated():
    legacy = {
        "model_backend": "tabular_sklearn",
        "gene_feature_loading": "range",
    }
    migrated, _summary = _migrate_validation_section(legacy)
    assert migrated["backend_profiles"]["ecdf"]["params"]["gene_feature_loading"] == "range"
    assert migrated["backend_profiles"]["tabular_sklearn"]["params"]["gene_feature_loading"] == "range"
    cfg = MonteCarloConfig.model_validate(_base_payload() | {"backend_profiles": migrated["backend_profiles"]})
    switched = cfg.with_backend_selection("tabular_sklearn")
    assert switched.gene_feature_loading == "range"


def test_stability_early_stop_requires_min_iterations_within_budget():
    payload = _base_payload()
    payload["n_iterations"] = 5
    payload["stability_early_stop_enabled"] = True
    payload["stability_min_iterations"] = 6
    with pytest.raises(ValueError, match="stability_min_iterations must be <= n_iterations"):
        MonteCarloConfig.model_validate(payload)


def test_stability_early_stop_requires_window_smaller_than_min_iterations():
    payload = _base_payload()
    payload["n_iterations"] = 10
    payload["stability_early_stop_enabled"] = True
    payload["stability_min_iterations"] = 5
    payload["stability_convergence_window"] = 5
    with pytest.raises(ValueError, match="stability_convergence_window must be smaller"):
        MonteCarloConfig.model_validate(payload)


def test_feature_selection_defaults_and_validation():
    cfg = MonteCarloConfig.model_validate(_base_payload())
    assert cfg.feature_selection.enabled is False
    assert cfg.feature_selection.mode == "stability_filter"
    assert cfg.feature_selection.feature_families == ["dmp", "gene", "structural"]

    payload = _base_payload()
    payload["feature_selection"] = {"enabled": True, "mode": "bad_mode"}
    with pytest.raises(ValueError, match="feature_selection.mode"):
        MonteCarloConfig.model_validate(payload)
