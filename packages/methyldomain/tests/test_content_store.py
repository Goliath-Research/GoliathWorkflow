"""Unit tests for content-addressed action store (CAAS)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from methyl_domain.action_result import (
    ActionExecutionRecord,
    ArtifactRef,
    caas_entry_dir,
    caas_entry_manifest_path,
    instance_ledger_path,
)
from methyl_domain.content_store import (
    append_instance_ledger,
    caas_enabled,
    commit_artifacts_to_store,
    link_entry_into_place,
    resolve_project_root,
)


def _record(
    *,
    artifacts: list[ArtifactRef],
    input_sig: str = "in-sig",
    output_sig: str = "out-sig",
) -> ActionExecutionRecord:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return ActionExecutionRecord(
        action_name="validation.stability",
        capability="validation.stability",
        started_at_utc=now,
        finished_at_utc=now,
        duration_ms=1,
        artifacts=artifacts,
        action_revision="rev1",
        input_signature=input_sig,
        output_signature=output_sig,
        content_key="content-key-abc",
        hyperparam_set_id="hpset-1",
        task_output={"status": "ok"},
    )


def test_caas_enabled_defaults_on(monkeypatch) -> None:
    monkeypatch.delenv("METHYL_CAAS_ENABLED", raising=False)
    assert caas_enabled({}) is True
    assert caas_enabled({"caasEnabled": True}) is True
    assert caas_enabled({"caasEnabled": False}) is False
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "0")
    assert caas_enabled({}) is False
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "false")
    assert caas_enabled({}) is False
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    assert caas_enabled({}) is True


def test_resolve_project_root_from_mc_run_dir(tmp_path: Path) -> None:
    project_root = tmp_path / "Study"
    run_dir = project_root / "monte_carlo_runs" / "run_0001"
    run_dir.mkdir(parents=True)
    resolved = resolve_project_root({"runDir": str(run_dir)})
    assert resolved == project_root.resolve()


def test_commit_and_relink_uses_relative_symlink(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    project_root = tmp_path / "Study"
    stability_dir = project_root / "monte_carlo_runs" / "stability"
    stability_dir.mkdir(parents=True)
    summary = stability_dir / "stability_summary.json"
    summary.write_text("{}", encoding="utf-8")

    record = _record(artifacts=[ArtifactRef(path=str(summary), bytes=2)])
    commit_artifacts_to_store(
        project_root,
        "validation.stability",
        "content-key-rel",
        record,
        output_dir=stability_dir,
    )
    assert summary.is_symlink()
    target = os.readlink(summary)
    assert not os.path.isabs(target), f"expected relative symlink, got {target!r}"
    assert summary.resolve().is_file()


def test_commit_and_relink_directory_entry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    project_root = tmp_path / "Study"
    stability_dir = project_root / "monte_carlo_runs" / "stability"
    stability_dir.mkdir(parents=True)
    summary = stability_dir / "stability_summary.json"
    summary.write_text("{}", encoding="utf-8")

    record = _record(artifacts=[ArtifactRef(path=str(summary), bytes=2)])
    committed = commit_artifacts_to_store(
        project_root,
        "validation.stability",
        "content-key-abc",
        record,
        output_dir=stability_dir,
    )
    entry_dir = caas_entry_dir(project_root, "validation.stability", "content-key-abc")
    assert (entry_dir / "stability_summary.json").is_file()
    assert caas_entry_manifest_path(project_root, "validation.stability", "content-key-abc").is_file()
    assert summary.is_symlink()
    assert summary.resolve().parent == entry_dir.resolve()

    other_dir = project_root / "monte_carlo_runs" / "stability_alt"
    other_dir.mkdir(parents=True)
    other_summary = other_dir / "stability_summary.json"
    linked = link_entry_into_place(
        project_root,
        "validation.stability",
        "content-key-abc",
        output_dir=other_dir,
    )
    assert linked is not None
    assert other_summary.is_symlink()
    assert committed.content_key == "content-key-abc"


def test_cross_instance_reuse_same_content_key(tmp_path: Path) -> None:
    project_root = tmp_path / "Study"
    out_a = project_root / "monte_carlo_runs" / "stability"
    out_a.mkdir(parents=True)
    artifact = out_a / "stability_summary.json"
    artifact.write_text('{"a": 1}', encoding="utf-8")

    record = _record(artifacts=[ArtifactRef(path=str(artifact), bytes=len(artifact.read_bytes()))])
    commit_artifacts_to_store(
        project_root,
        "validation.stability",
        "key-shared",
        record,
        output_dir=out_a,
    )

    out_b = project_root / "other" / "stability"
    out_b.mkdir(parents=True)
    target = out_b / "stability_summary.json"
    linked = link_entry_into_place(
        project_root,
        "validation.stability",
        "key-shared",
        output_dir=out_b,
    )
    assert linked is not None
    assert target.is_symlink()
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def test_config_change_forks_new_entry(tmp_path: Path) -> None:
    project_root = tmp_path / "Study"
    out_dir = project_root / "stability"
    out_dir.mkdir(parents=True)
    artifact = out_dir / "stability_summary.json"
    artifact.write_text("v1", encoding="utf-8")

    record_v1 = _record(
        artifacts=[ArtifactRef(path=str(artifact), bytes=2)],
        input_sig="sig-v1",
        output_sig="out-v1",
    )
    commit_artifacts_to_store(project_root, "validation.stability", "key-v1", record_v1, output_dir=out_dir)

    if artifact.is_symlink():
        artifact.unlink()
    artifact.write_text("v2", encoding="utf-8")
    record_v2 = _record(
        artifacts=[ArtifactRef(path=str(artifact), bytes=2)],
        input_sig="sig-v2",
        output_sig="out-v2",
    )
    commit_artifacts_to_store(project_root, "validation.stability", "key-v2", record_v2, output_dir=out_dir)

    assert caas_entry_dir(project_root, "validation.stability", "key-v1").is_dir()
    assert caas_entry_dir(project_root, "validation.stability", "key-v2").is_dir()
    assert (caas_entry_dir(project_root, "validation.stability", "key-v1") / "stability_summary.json").read_text() == "v1"
    assert (caas_entry_dir(project_root, "validation.stability", "key-v2") / "stability_summary.json").read_text() == "v2"


def test_instance_ledger_records_action_run_key(tmp_path: Path) -> None:
    project_root = tmp_path / "Study"
    append_instance_ledger(
        project_root,
        "hpset-abc",
        action_name="pipeline.centroid",
        run_key="1_CG_all",
        content_key="ck-123",
    )
    ledger_path = instance_ledger_path(project_root, "hpset-abc")
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert payload["hyperparam_set_id"] == "hpset-abc"
    assert payload["entries"]["pipeline.centroid:1_CG_all"]["content_key"] == "ck-123"
