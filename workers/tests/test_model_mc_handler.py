"""Tests for workflow-facing model-MC handler options."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from methyl_worker.handlers.validation import _handle_validation_model_mc
from methyl_worker.task_models.runtime_models import TaskRuntimeContext
from methyl_worker.task_models.validation_models import ModelMcTaskInput


def test_model_mc_handler_forwards_strict_artifact_reuse(tmp_path: Path) -> None:
    mc_root = tmp_path / "monte_carlo_runs"
    production_dir = mc_root / "production"
    config = SimpleNamespace(production_output_dir=str(production_dir))
    input_model = ModelMcTaskInput(
        projectPath=str(tmp_path / "project.json"),
        requireArtifactReuse=True,
    )

    with (
        patch(
            "methyl_worker.handlers.validation._load_mc_config",
            return_value=(config, tmp_path / "project.json"),
        ),
        patch(
            "methyl_validation.model_mc_runner.run_model_mc_all",
            return_value={
                "modelMcRoot": str(mc_root / "model_mc"),
                "nSharedIterations": 10,
            },
        ) as runner,
    ):
        output = _handle_validation_model_mc(
            "validation.model-mc",
            "validation.model_mc",
            input_model,
            runtime=TaskRuntimeContext(),
            mc_root=mc_root,
        )

    assert output.n_iterations == 10
    assert runner.call_args.kwargs["require_artifact_reuse"] is True
