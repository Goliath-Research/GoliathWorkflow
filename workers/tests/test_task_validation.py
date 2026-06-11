"""Tests for workflow task input/output schema validation."""

from __future__ import annotations

import pytest

from methyl_worker.task_validation import (
    TASK_VALIDATION_ERROR_CODE,
    TaskValidationError,
    validate_task_input,
    validate_task_output,
    try_validate_task_input,
    try_validate_task_output,
)


def test_pipeline_centroid_input_accepts_valid_payload() -> None:
    validate_task_input(
        "pipeline.centroid",
        "methyl-centroid",
        {"tool": "methyl-centroid", "project": "demo", "phase": "train"},
    )


def test_pipeline_centroid_input_rejects_missing_tool() -> None:
    with pytest.raises(TaskValidationError) as exc:
        validate_task_input("pipeline.centroid", "methyl-centroid", {"project": "demo"})
    assert exc.value.direction == "input"
    assert exc.value.action_name == "pipeline.centroid"


def test_pipeline_centroid_output_accepts_minimal() -> None:
    validate_task_output("pipeline.centroid", "methyl-centroid", {"status": "ok"})


def test_pipeline_centroid_output_rejects_bad_status_type() -> None:
    with pytest.raises(TaskValidationError):
        validate_task_output("pipeline.centroid", "methyl-centroid", {"status": 123})


def test_unknown_action_skips_validation() -> None:
    validate_task_input("unknown.action", None, {"anything": True})
    validate_task_output("unknown.action", None, {"anything": True})


def test_validation_plan_resolves_by_capability() -> None:
    validate_task_input(
        "validation.plan_iterations",
        "validation.plan-iterations",
        {"projectPath": "/work/demo/project.json", "featureIterations": 3},
    )


def test_try_validate_returns_message() -> None:
    msg = try_validate_task_input("pipeline.detector", None, {})
    assert msg is not None
    assert "input_json failed schema validation" in msg


def test_task_validation_error_code_constant() -> None:
    assert TASK_VALIDATION_ERROR_CODE == 4001
