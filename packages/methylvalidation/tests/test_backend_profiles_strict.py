from __future__ import annotations

import pytest

from methyl_validation.cli import _resolve_model_mc_backends
from methyl_validation.config import MonteCarloConfig
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
