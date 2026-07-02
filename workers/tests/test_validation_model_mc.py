"""Unit tests for validation.model_mc handler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import methyl_validation.model_mc_runner as model_mc_runner
from methyl_worker import handlers
from methyl_worker.task_models.validation_models import ModelMcTaskInput


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
        "nSharedIterations": 3,
    }

    task_input = ModelMcTaskInput.model_validate(
        {
            "projectPath": str(tmp_path / "project.json"),
            "monteCarloRunsRoot": str(mc_root),
        }
    )

    with patch.object(model_mc_runner, "run_model_mc_all", return_value=fake_result) as mock_run:
        with patch.object(handlers, "_load_mc_config") as mock_cfg:
            config = MagicMock()
            config.production_output_dir = None
            mock_cfg.return_value = (config, tmp_path / "project.json")
            out = handlers._handle_validation_model_mc(
                "validation.model-mc",
                "validation.model_mc",
                task_input,
            )

    mock_run.assert_called_once()
    assert out.modelMcRoot.endswith("model_mc")
    assert out.n_iterations == 3


def test_load_mc_config_ignores_non_planner_task_fields(tmp_path: Path) -> None:
    """Stability-shaped task input carries fields ValidationPlanRequest forbids.

    _load_mc_config must filter input_json down to planner fields (and normalize
    project -> projectPath) instead of validating the whole payload, otherwise
    pydantic raises extra_forbidden on tool/project/monteCarloRunsRoot/outputDir.
    """
    project_json = tmp_path / "project.json"
    project_json.write_text("{}", encoding="utf-8")

    input_json = {
        "tool": "validation.stability",
        "project": str(project_json),
        "monteCarloRunsRoot": None,
        "outputDir": None,
        "featureIterations": None,
        "seed": None,
    }

    captured = {}

    def fake_load(base_project, request, **_kwargs):
        captured["projectPath"] = request.projectPath
        return MagicMock()

    with patch(
        "methyl_validation.workflow_planner.resolve_base_project_json",
        return_value=project_json,
    ):
        with patch(
            "methyl_validation.workflow_planner._load_config_from_project",
            side_effect=fake_load,
        ):
            config, base = handlers._load_mc_config(input_json)

    assert base == project_json
    assert captured["projectPath"] == str(project_json)
