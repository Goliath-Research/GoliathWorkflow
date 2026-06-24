"""Tests for validation.plan-iterations worker handler."""

from __future__ import annotations

from unittest.mock import patch

from methyl_worker.handlers import execute_task


def test_validation_plan_iterations_handler() -> None:
    fake_context = {
        "projectPath": "/work/demo",
        "iterations": [
            {
                "run_id": "feature_run_0001",
                "runId": "feature_run_0001",
                "phase": "feature",
                "projectPath": "/work/demo/monte_carlo_runs/run_0001/project.json",
                "taskConfig": {"runId": "feature_run_0001", "phase": "feature", "iteration": 1},
            }
        ],
    }
    with patch(
        "methyl_validation.workflow_planner.plan_validation_context",
        return_value=fake_context,
    ):
        result = execute_task(
            "validation.plan-iterations",
            "validation.plan_iterations",
            {"projectPath": "/cfg/project.json", "featureIterations": 1},
        )
    out = result.output.model_dump()
    assert out["status"] == "ok"
    assert out["n_iterations"] == 1
    assert out["iterations"][0]["run_id"] == "feature_run_0001"
