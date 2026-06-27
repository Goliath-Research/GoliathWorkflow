"""Tests for signature-based action skip/replay."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from methyl_domain.action_result import ActionExecutionRecord, atomic_write_action_result, manifest_path_for
from pydantic import BaseModel

from methyl_worker.action_catalog import find_catalog_entry
from methyl_worker.action_execution import execution_result_from_output, validate_input
from methyl_worker.action_skip import (
    compute_action_revision,
    compute_input_signature,
    maybe_skip_action,
    record_action_execution,
    verify_artifacts,
)
from methyl_worker.handlers import execute_task
from methyl_worker.task_validation import strip_runtime_input
from methyl_worker.task_models.validation_models import StabilitySummary, ValidationStabilityOutput


def _write_study_project(path: Path, tmp_path: Path) -> None:
    (tmp_path / "s.csv").write_text("S1\n", encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "output_base": str(tmp_path),
                "project_name": "Study",
                "chromosomes": ["1"],
                "contexts": ["CG"],
                "group1": {"label": "g1", "sample_paths": [str(tmp_path / "s.csv")]},
                "group2": {"label": "g2", "sample_paths": [str(tmp_path / "s.csv")]},
            }
        ),
        encoding="utf-8",
    )


def test_compute_input_signature_stable_for_same_payload() -> None:
    entry = find_catalog_entry("validation.stability")
    assert entry is not None

    class FakeInput(BaseModel):
        projectPath: str

    model = FakeInput(projectPath="/work/p/project.json")
    payload = {"projectPath": "/work/p/project.json"}
    assert compute_input_signature(entry, payload, model) == compute_input_signature(
        entry, payload, model
    )


def test_verify_artifacts_detects_size_change(tmp_path: Path) -> None:
    from methyl_domain.action_result import ArtifactRef

    path = tmp_path / "out.json"
    path.write_text("{}", encoding="utf-8")
    ref = ArtifactRef(path=str(path), bytes=2)
    assert verify_artifacts([ref]) is True
    path.write_text("{}\n", encoding="utf-8")
    assert verify_artifacts([ref]) is False


def test_maybe_skip_replays_when_manifest_matches(tmp_path: Path) -> None:
    entry = find_catalog_entry("validation.stability")
    assert entry is not None

    mc_root = tmp_path / "monte_carlo_runs"
    stability_dir = mc_root / "stability"
    stability_dir.mkdir(parents=True)
    summary_path = stability_dir / "stability_summary.json"
    summary_path.write_text("{}", encoding="utf-8")

    project = tmp_path / "configs" / "project.json"
    _write_study_project(project, tmp_path)

    input_json = {
        "projectPath": str(project),
        "monteCarloRunsRoot": str(mc_root),
        "outputDir": str(stability_dir),
        "resolvedConfig": {"n_iterations": 2, "stability_dmp_freq": 0.7},
    }

    input_model = validate_input(entry, strip_runtime_input(input_json))
    output = ValidationStabilityOutput(
        status="ok",
        outputDir=str(stability_dir),
        summary=StabilitySummary(summary_json_path=str(summary_path), n_iterations=2),
    )
    record_action_execution(entry, input_json, input_model, execution_result_from_output(output))

    assert manifest_path_for(stability_dir, entry.action_name, "default").is_file()
    skipped = maybe_skip_action(entry, input_json)
    assert skipped is not None
    assert skipped.output.status == "skipped"


def test_maybe_skip_works_with_workflow_node_key(tmp_path: Path) -> None:
    """workflowNodeKey is runtime-only; must not break validate_input inside maybe_skip_action."""
    entry = find_catalog_entry("validation.stability")
    assert entry is not None

    mc_root = tmp_path / "monte_carlo_runs"
    stability_dir = mc_root / "stability"
    stability_dir.mkdir(parents=True)
    summary_path = stability_dir / "stability_summary.json"
    summary_path.write_text("{}", encoding="utf-8")

    project = tmp_path / "project.json"
    _write_study_project(project, tmp_path)

    task_input = {
        "projectPath": str(project),
        "monteCarloRunsRoot": str(mc_root),
        "outputDir": str(stability_dir),
        "resolvedConfig": {"n_iterations": 1},
    }
    input_model = validate_input(entry, strip_runtime_input(task_input))
    output = ValidationStabilityOutput(
        status="ok",
        outputDir=str(stability_dir),
        summary=StabilitySummary(summary_json_path=str(summary_path), n_iterations=1),
    )
    record_action_execution(entry, task_input, input_model, execution_result_from_output(output))

    skip_input = {**task_input, "workflowNodeKey": "stability", "forceRerun": False}
    skipped = maybe_skip_action(entry, skip_input)
    assert skipped is not None
    assert skipped.output.status == "skipped"


def test_force_rerun_bypasses_skip(tmp_path: Path) -> None:
    entry = find_catalog_entry("validation.stability")
    assert entry is not None
    stability_dir = tmp_path / "stability"
    stability_dir.mkdir()
    input_json = {
        "projectPath": str(tmp_path / "missing.json"),
        "outputDir": str(stability_dir),
        "forceRerun": True,
    }
    assert maybe_skip_action(entry, input_json) is None


def test_plan_iterations_skip_blocked_by_legacy_mc_run_project(tmp_path: Path) -> None:
    from methyl_worker.task_models.validation_models import ValidationPlanTaskOutput

    entry = find_catalog_entry("validation.plan_iterations")
    assert entry is not None

    mc_root = tmp_path / "Study" / "monte_carlo_runs"
    legacy_run = mc_root / "run_0002"
    legacy_run.mkdir(parents=True)
    (legacy_run / "project.json").write_text(
        json.dumps({"project_name": "run_0002", "step_config": {"detection": {"alpha": 0.05}}}),
        encoding="utf-8",
    )

    project = tmp_path / "configs" / "project.json"
    _write_study_project(project, tmp_path)

    input_json = {
        "projectPath": str(project),
        "featureIterations": 10,
        "resolvedConfig": {"n_iterations": 10},
    }
    input_model = validate_input(entry, strip_runtime_input(input_json))
    output = ValidationPlanTaskOutput(status="ok", n_iterations=10, iterations=[])
    record_action_execution(entry, input_json, input_model, execution_result_from_output(output))

    assert manifest_path_for(mc_root, entry.action_name, "default").is_file()
    skipped = maybe_skip_action(entry, input_json)
    assert skipped is None


def test_normalize_task_input_preserves_force_rerun() -> None:
    from methyl_worker.task_validation import normalize_task_input

    normalized = normalize_task_input(
        "validation.plan_iterations",
        "validation.plan-iterations",
        {
            "projectPath": "/work/p/project.json",
            "featureIterations": 10,
            "forceRerun": True,
            "workflowNodeKey": "plan_iterations",
            "extraTemplateField": "dropped",
        },
    )
    assert normalized.get("forceRerun") is True
    assert normalized.get("workflowNodeKey") == "plan_iterations"
    assert "extraTemplateField" not in normalized


def test_execute_task_honors_force_rerun_after_normalize(tmp_path: Path, monkeypatch) -> None:
    """Engine path: normalize_task_input must not strip forceRerun before maybe_skip_action."""
    from methyl_worker.task_validation import normalize_task_input

    entry = find_catalog_entry("validation.stability")
    assert entry is not None
    stability_dir = tmp_path / "stability"
    stability_dir.mkdir(parents=True)
    project = tmp_path / "project.json"
    project.write_text("{}", encoding="utf-8")

    revision = compute_action_revision(entry)
    record = ActionExecutionRecord(
        action_name=entry.action_name,
        capability=entry.capability,
        started_at_utc=datetime.now(timezone.utc).replace(microsecond=0),
        finished_at_utc=datetime.now(timezone.utc).replace(microsecond=0),
        duration_ms=1,
        action_revision=revision,
        input_signature="sig",
        output_signature="outsig",
        task_output={"status": "ok", "outputDir": str(stability_dir), "summary": {}},
        artifacts=[],
    )
    atomic_write_action_result(
        manifest_path_for(stability_dir, entry.action_name, "default"),
        record,
    )

    raw = {
        "projectPath": str(project),
        "monteCarloRunsRoot": str(tmp_path / "mc"),
        "outputDir": str(stability_dir),
        "forceRerun": True,
    }
    normalized = normalize_task_input(entry.action_name, entry.capability, raw)
    assert normalized.get("forceRerun") is True

    run_calls: list = []

    class FakeAction:
        def execute(self, _input_json):
            run_calls.append(1)
            return execution_result_from_output(
                ValidationStabilityOutput(
                    status="ok",
                    outputDir=str(stability_dir),
                    summary=StabilitySummary(),
                )
            )

    monkeypatch.setattr(
        "methyl_worker.handlers.build_action_from_catalog",
        lambda _entry, _mod: FakeAction(),
    )

    result = execute_task(entry.capability, entry.action_name, normalized)
    assert run_calls, "forceRerun should bypass skip and execute handler"
    assert result.output.status == "ok"


def test_execute_task_skips_validation_stability_when_manifest_exists(tmp_path: Path, monkeypatch) -> None:
    entry = find_catalog_entry("validation.stability")
    assert entry is not None
    mc_root = tmp_path / "monte_carlo_runs"
    stability_dir = mc_root / "stability"
    stability_dir.mkdir(parents=True)
    summary_path = stability_dir / "stability_summary.json"
    summary_path.write_text("{}", encoding="utf-8")

    project = tmp_path / "project.json"
    _write_study_project(project, tmp_path)

    revision = compute_action_revision(entry)
    input_sig = "abc123"
    output_sig = "def456"
    started = datetime.now(timezone.utc).replace(microsecond=0)
    record = ActionExecutionRecord(
        action_name=entry.action_name,
        capability=entry.capability,
        started_at_utc=started,
        finished_at_utc=started,
        duration_ms=1,
        action_revision=revision,
        input_signature=input_sig,
        output_signature=output_sig,
        task_output={
            "status": "ok",
            "outputDir": str(stability_dir),
            "summary": {"summary_json_path": str(summary_path), "n_iterations": 1},
        },
        artifacts=[],
    )
    manifest = manifest_path_for(stability_dir, entry.action_name, "default")
    atomic_write_action_result(manifest, record)

    monkeypatch.setattr(
        "methyl_worker.action_skip.compute_input_signature",
        lambda *_args, **_kwargs: input_sig,
    )
    monkeypatch.setattr(
        "methyl_worker.action_skip.compute_output_signature",
        lambda *_args, **_kwargs: output_sig,
    )
    monkeypatch.setattr("methyl_worker.action_skip.verify_artifacts", lambda _arts: True)

    result = execute_task(
        entry.capability,
        entry.action_name,
        {
            "projectPath": str(project),
            "monteCarloRunsRoot": str(mc_root),
            "outputDir": str(stability_dir),
            "resolvedConfig": {"n_iterations": 1},
        },
    )
    assert result.output.status == "skipped"
