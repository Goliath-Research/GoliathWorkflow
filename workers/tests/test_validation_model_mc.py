"""Unit tests for validation.model_mc handler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import methyl_validation.model_mc_runner as model_mc_runner
from methyl_worker import handlers


def test_model_mc_handler_delegates_to_runner(tmp_path: Path) -> None:
    production = tmp_path / "production"
    production.mkdir()
    (production / "project.json").write_text("{}", encoding="utf-8")
    mc_root = tmp_path / "monte_carlo_runs"
    mc_root.mkdir()

    fake_result = {
        "status": "ok",
        "modelMcRoot": str(mc_root / "model_mc"),
        "backends": ["ecdf"],
    }

    with patch.object(model_mc_runner, "run_model_mc_all", return_value=fake_result) as mock_run:
        with patch.object(handlers, "_load_mc_config") as mock_cfg:
            config = MagicMock()
            config.production_output_dir = None
            mock_cfg.return_value = (config, tmp_path / "project.json")
            out = handlers._handle_validation_model_mc(
                "validation.model-mc",
                "validation.model_mc",
                {
                    "projectPath": str(tmp_path / "project.json"),
                    "monteCarloRunsRoot": str(mc_root),
                    "productionOutputDir": str(production),
                },
            )

    mock_run.assert_called_once()
    assert out["modelMcRoot"].endswith("model_mc")
    assert out["backends"] == ["ecdf"]
