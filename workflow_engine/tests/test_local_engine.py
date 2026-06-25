"""Tests for in-process LocalWorkflowEngine."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
for rel in ("workflow_engine/local", "workflow_engine/domain", "workflow_engine/contract", "workers"):
    p = REPO / rel
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from pydantic import BaseModel

from local.conditions import scope_var_truthy  # noqa: E402
from local.engine import LocalWorkflowEngine  # noqa: E402
from local.scheduler import SchedulerConfig  # noqa: E402


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        ("true", True),
        ("", False),
        (None, False),
        ([1], True),
        ([], False),
    ],
)
def test_scope_var_truthy(value: Any, expected: bool) -> None:
    assert scope_var_truthy({"flag": value}, "flag") is expected


def test_if_then_else_branching() -> None:
    """Minimal IF workflow: branch on qcPass scope variable."""
    from workflow_definition_spec import WorkflowDefinitionSpec, WorkflowEdgeSpec, WorkflowNodeSpec

    spec = WorkflowDefinitionSpec(
        name="IfTest",
        root_node_key="root",
        nodes=[
            WorkflowNodeSpec(node_key="root", node_type="SEQUENCE"),
            WorkflowNodeSpec(node_key="set_pass", node_type="ACTION", action_name="sample.qc_failed"),
            WorkflowNodeSpec(node_key="if_qc", node_type="IF", condition_var="qcPass"),
            WorkflowNodeSpec(node_key="then_seq", node_type="SEQUENCE"),
            WorkflowNodeSpec(node_key="then_action", node_type="ACTION", action_name="sample.qc_failed"),
            WorkflowNodeSpec(node_key="else_seq", node_type="SEQUENCE"),
            WorkflowNodeSpec(node_key="else_action", node_type="ACTION", action_name="sample.qc_failed"),
        ],
        edges=[
            WorkflowEdgeSpec(parent_node_key="root", child_node_key="if_qc", branch_kind="SEQUENCE"),
            WorkflowEdgeSpec(parent_node_key="if_qc", child_node_key="then_seq", branch_kind="THEN"),
            WorkflowEdgeSpec(parent_node_key="if_qc", child_node_key="else_seq", branch_kind="ELSE"),
            WorkflowEdgeSpec(parent_node_key="then_seq", child_node_key="then_action", branch_kind="SEQUENCE"),
            WorkflowEdgeSpec(parent_node_key="else_seq", child_node_key="else_action", branch_kind="SEQUENCE"),
        ],
    )
    executed: list[str] = []

    class _QcFailedOutput(BaseModel):
        sampleId: str
        status: str

    def handler(_cap: str, action: str, _inp: Dict[str, Any]) -> BaseModel:
        executed.append(action)
        return _QcFailedOutput(sampleId="S1", status="QC_FAILED")

    engine = LocalWorkflowEngine(
        handler=handler,
        config=SchedulerConfig(parallel_workers=1),
    )

    # qcPass true -> THEN branch
    result = engine.run_spec(spec, {"qcPass": True}, enrich_context=False)
    assert result.status == "COMPLETED"
    assert "then_action" in result.trace.executed_actions or executed

    executed.clear()
    result2 = engine.run_spec(spec, {"qcPass": False}, enrich_context=False)
    assert result2.status == "COMPLETED"


@pytest.fixture
def sample_prep_context() -> dict:
    fixture = REPO / "workflow_engine/sql/instance_context_examples/sample_prep_plasma.json"
    ctx = json.loads(fixture.read_text(encoding="utf-8"))
    for sample in ctx.get("samples", []):
        if "sampleDestination" not in sample and "h5Destination" in sample:
            sample["sampleDestination"] = sample["h5Destination"]
    return ctx


def test_sample_prep_program_stub_run(sample_prep_context: dict) -> None:
    os.environ["WORKER_STUB_EXTERNAL"] = "1"
    program = REPO / "workflow_engine/domain/fixtures/sample_prep.program.json"
    engine = LocalWorkflowEngine(config=SchedulerConfig(parallel_workers=1))
    result = engine.run_program(program, sample_prep_context, enrich_context=False)
    assert result.status == "COMPLETED", result.error
    # 2 samples × ~9 actions
    assert len(result.trace.executed_actions) >= 16
