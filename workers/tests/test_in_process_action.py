"""Tests for InProcessAction handler dispatch."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from methyl_worker.action_catalog import find_catalog_entry
from methyl_worker.actions.base import InProcessAction, _handler_accepts_runtime
from methyl_worker.task_models.runtime_models import TaskRuntimeContext


class _SampleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projectPath: str


class _SampleOutput(BaseModel):
    status: str = "ok"


def _three_arg_handler(_cap: str, _name: str, input: BaseModel) -> _SampleOutput:
    return _SampleOutput()


def _four_arg_handler(
    _cap: str,
    _name: str,
    input: BaseModel,
    runtime: TaskRuntimeContext,
) -> _SampleOutput:
    if runtime.workflowNodeKey == "boom":
        raise TypeError("internal handler failure")
    return _SampleOutput()


def test_handler_accepts_runtime_detects_signatures() -> None:
    assert _handler_accepts_runtime(_three_arg_handler) is False
    assert _handler_accepts_runtime(_four_arg_handler) is True


def test_in_process_action_calls_three_arg_handler_without_runtime() -> None:
    entry = find_catalog_entry("validation.plan_iterations")
    assert entry is not None
    action = InProcessAction(_three_arg_handler, entry=entry)
    result = action.execute({"projectPath": "/work/demo/project.json", "featureIterations": 1})
    assert result.result_code == 0


def test_in_process_action_propagates_internal_type_error_from_four_arg_handler() -> None:
    entry = find_catalog_entry("validation.plan_iterations")
    assert entry is not None
    action = InProcessAction(_four_arg_handler, entry=entry)
    with pytest.raises(TypeError, match="internal handler failure"):
        action.execute(
            {
                "projectPath": "/work/demo/project.json",
                "featureIterations": 1,
                "workflowNodeKey": "boom",
            }
        )


def test_in_process_action_passes_runtime_to_four_arg_handler() -> None:
    captured: dict[str, TaskRuntimeContext] = {}

    def _capture_runtime(
        _cap: str,
        _name: str,
        _input: BaseModel,
        runtime: TaskRuntimeContext,
    ) -> _SampleOutput:
        captured["runtime"] = runtime
        return _SampleOutput()

    entry = find_catalog_entry("validation.plan_iterations")
    assert entry is not None
    action = InProcessAction(_capture_runtime, entry=entry)
    action.execute(
        {
            "projectPath": "/work/demo/project.json",
            "featureIterations": 1,
            "workflowNodeKey": "plan-1",
            "resolvedConfig": {"n_iterations": 2},
        }
    )
    runtime = captured["runtime"]
    assert runtime.workflowNodeKey == "plan-1"
    assert runtime.validationProfile is not None
    assert runtime.validationProfile.n_iterations == 2
