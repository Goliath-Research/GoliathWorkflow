"""Tests for validation action_run_log.jsonl."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from methyl_worker.action_run_log import action_run_log_path, append_action_run_log
from methyl_worker.handlers import execute_task
from methyl_worker.task_models.validation_models import ValidationPlanTaskOutput


def test_append_action_run_log_writes_jsonl(tmp_path: Path) -> None:
    append_action_run_log(
        tmp_path,
        action="validation.stability",
        capability="validation.stability",
        result_code=0,
        inputs={"projectPath": "/work/p/project.json"},
        outputs={"status": "ok"},
    )
    log_path = action_run_log_path(tmp_path)
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["action"] == "validation.stability"
    assert record["result_code"] == 0


def test_execute_task_appends_validation_action_log(tmp_path: Path, monkeypatch) -> None:
    mc_root = tmp_path / "monte_carlo_runs"
    mc_root.mkdir()
    project = tmp_path / "project.json"
    project.write_text("{}", encoding="utf-8")

    fake_output = ValidationPlanTaskOutput(status="ok", n_iterations=0)

    class FakeAction:
        def execute(self, _input_json):
            from methyl_worker.action_execution import ActionExecutionResult

            return ActionExecutionResult(result_code=0, output=fake_output)

    monkeypatch.setattr(
        "methyl_worker.handlers.build_action_from_catalog",
        lambda _entry, _mod: FakeAction(),
    )
    with patch("methyl_worker.handlers._resolve_monte_carlo_runs_root", return_value=mc_root):
        execute_task(
            "validation.plan-iterations",
            "validation.plan_iterations",
            {"projectPath": str(project), "monteCarloRunsRoot": str(mc_root)},
        )

    log_path = action_run_log_path(mc_root)
    assert log_path.is_file()
    record = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert record["action"] == "validation.plan_iterations"
