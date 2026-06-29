"""Tests for validation.plan-iterations worker handler."""

from __future__ import annotations

from unittest.mock import patch

from methyl_validation.workflow_planner import ValidationPlanContext, ValidationPlannedIteration
from methyl_worker.handlers import execute_task


def test_validation_plan_iterations_handler() -> None:
    fake_context = ValidationPlanContext(
        projectPath="/work/demo",
        iterations=[
            ValidationPlannedIteration.model_validate(
                {
                    "run_id": "feature_run_0001",
                    "runId": "feature_run_0001",
                    "phase": "feature",
                    "runDir": "/work/demo/monte_carlo_runs/run_0001",
                    "projectPath": "/work/demo/monte_carlo_runs/run_0001/project.json",
                    "taskConfig": {"runId": "feature_run_0001", "phase": "feature", "iteration": 1},
                }
            )
        ],
        validationPlan={
            "baseProject": "/cfg/project.json",
            "layout": "binary",
            "featureIterations": 1,
            "qualityIterations": 0,
            "trainFraction": 0.8,
            "monteCarloRunsRoot": "/work/demo/monte_carlo_runs",
        },
    )
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
    assert out["iterations"][0]["projectPath"] == "/work/demo/monte_carlo_runs/run_0001/project.json"
    assert out["iterations"][0]["runDir"] == "/work/demo/monte_carlo_runs/run_0001"
    iter_ref = result.output.iterations[0]
    assert iter_ref.runDir == "/work/demo/monte_carlo_runs/run_0001"
    assert iter_ref.projectPath == "/work/demo/monte_carlo_runs/run_0001/project.json"


def test_validation_plan_iterations_maps_snake_case_fields() -> None:
    fake_context = ValidationPlanContext(
        projectPath="/work/demo",
        iterations=[
            ValidationPlannedIteration.model_validate(
                {
                    "runId": "feature_run_0000",
                    "iteration": 0,
                    "phase_index": 3,
                    "runDir": "/work/demo/monte_carlo_runs/run_0000",
                    "projectPath": "/work/demo/monte_carlo_runs/run_0000/project.json",
                }
            )
        ],
        validationPlan={
            "baseProject": "/cfg/project.json",
            "layout": "binary",
            "featureIterations": 1,
            "qualityIterations": 0,
            "trainFraction": 0.8,
            "monteCarloRunsRoot": "/work/demo/monte_carlo_runs",
        },
    )
    with patch(
        "methyl_validation.workflow_planner.plan_validation_context",
        return_value=fake_context,
    ):
        result = execute_task(
            "validation.plan-iterations",
            "validation.plan_iterations",
            {"projectPath": "/cfg/project.json", "featureIterations": 1},
        )
    iter_ref = result.output.iterations[0]
    assert iter_ref.iteration == 0
    assert iter_ref.runDir == "/work/demo/monte_carlo_runs/run_0000"
    assert iter_ref.projectPath == "/work/demo/monte_carlo_runs/run_0000/project.json"
