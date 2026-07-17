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


def test_shared_output_dir_uses_flat_commit(tmp_path: Path, monkeypatch) -> None:
    """Sibling chromosome files in one centroids/all dir must not tree-steal each other."""
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    project_root = tmp_path / "Study"
    out_dir = project_root / "monte_carlo_runs" / "_centroid_seed" / "centroids" / "all"
    out_dir.mkdir(parents=True)
    chr1 = out_dir / "1-CG.h5"
    chr1.write_bytes(b"one")
    chr2 = out_dir / "2-CG.h5"
    chr2.write_bytes(b"two")

    record = _record(
        artifacts=[ArtifactRef(path=str(chr1), bytes=3)],
        input_sig="sig-chr1",
        output_sig="out-chr1",
    )
    commit_artifacts_to_store(
        project_root,
        "pipeline.centroid",
        "key-chr1",
        record,
        output_dir=out_dir,
    )
    assert chr1.is_symlink()
    assert not os.path.isabs(os.readlink(chr1))
    assert chr1.resolve().is_file()
    # Sibling must remain a real file (not moved into chr1's CAAS entry).
    assert chr2.is_file() and not chr2.is_symlink()
    assert chr2.read_bytes() == b"two"


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


def test_plan_iterations_preserves_run_relative_paths(tmp_path: Path, monkeypatch) -> None:
    """Same-basename files under run_####/ must not collapse into one CAAS blob."""
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    project_root = tmp_path / "Study"
    mc_root = project_root / "monte_carlo_runs"
    mc_root.mkdir(parents=True)
    # Unowned sibling forces flat (non-tree) commit — the plan_iterations case.
    (mc_root / "queue").mkdir()
    (mc_root / "action_run_log.jsonl").write_text("{}\n", encoding="utf-8")

    artifacts: list[ArtifactRef] = []
    for i in (1, 2):
        run_dir = mc_root / f"run_{i:04d}"
        run_dir.mkdir()
        project = run_dir / "project.json"
        project.write_text(json.dumps({"run": i}), encoding="utf-8")
        train = run_dir / "train_control.csv"
        train.write_text(f"sample\ns{i}\n", encoding="utf-8")
        artifacts.append(ArtifactRef(path=str(project), bytes=project.stat().st_size))
        artifacts.append(ArtifactRef(path=str(train), bytes=train.stat().st_size))

    record = _record(
        artifacts=artifacts,
        input_sig="sig-plan",
        output_sig="out-plan",
    )
    record = record.model_copy(update={"action_name": "validation.plan_iterations"})
    commit_artifacts_to_store(
        project_root,
        "validation.plan_iterations",
        "key-plan",
        record,
        output_dir=mc_root,
    )

    entry_dir = caas_entry_dir(project_root, "validation.plan_iterations", "key-plan")
    assert (entry_dir / "run_0001" / "project.json").is_file()
    assert (entry_dir / "run_0002" / "project.json").is_file()
    assert json.loads((entry_dir / "run_0001" / "project.json").read_text()) == {"run": 1}
    assert json.loads((entry_dir / "run_0002" / "project.json").read_text()) == {"run": 2}

    for i in (1, 2):
        link = mc_root / f"run_{i:04d}" / "project.json"
        assert link.is_symlink()
        assert not os.path.isabs(os.readlink(link))
        assert json.loads(link.read_text(encoding="utf-8")) == {"run": i}
        train_link = mc_root / f"run_{i:04d}" / "train_control.csv"
        assert train_link.is_symlink()
        assert train_link.read_text(encoding="utf-8").startswith("sample")


def test_caas_skip_relinks_after_product_tree_wipe(tmp_path: Path, monkeypatch) -> None:
    """Manifests must record CAAS blob paths so verify/relink works without product files."""
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    project_root = tmp_path / "Study"
    stability_dir = project_root / "monte_carlo_runs" / "stability"
    stability_dir.mkdir(parents=True)
    summary = stability_dir / "stability_summary.json"
    summary.write_text('{"n": 1}', encoding="utf-8")

    record = _record(
        artifacts=[ArtifactRef(path=str(summary), bytes=summary.stat().st_size)],
        input_sig="sig-wipe",
        output_sig="out-wipe",
    )
    committed = commit_artifacts_to_store(
        project_root,
        "validation.stability",
        "key-wipe",
        record,
        output_dir=stability_dir,
    )
    entry_dir = caas_entry_dir(project_root, "validation.stability", "key-wipe")
    assert all(Path(a.path).is_relative_to(entry_dir.resolve()) for a in committed.artifacts)

    import shutil

    shutil.rmtree(stability_dir)
    stability_dir.mkdir(parents=True)

    from methyl_domain.content_store import read_caas_entry, verify_entry_artifacts

    entry = read_caas_entry(project_root, "validation.stability", "key-wipe")
    assert entry is not None
    assert verify_entry_artifacts(entry)
    linked = link_entry_into_place(
        project_root,
        "validation.stability",
        "key-wipe",
        output_dir=stability_dir,
    )
    assert linked is not None
    assert (stability_dir / "stability_summary.json").is_symlink()
    assert json.loads((stability_dir / "stability_summary.json").read_text()) == {"n": 1}


def test_plan_iterations_recommit_through_existing_caas_symlinks_does_not_steal(
    tmp_path: Path, monkeypatch
) -> None:
    """A second content-key must not flatten/steal blobs from the first via symlink resolve()."""
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    project_root = tmp_path / "Study"
    mc_root = project_root / "monte_carlo_runs"
    mc_root.mkdir(parents=True)
    (mc_root / "queue").mkdir()
    (mc_root / "action_run_log.jsonl").write_text("{}\n", encoding="utf-8")

    artifacts_v1: list[ArtifactRef] = []
    for i in (1, 2):
        run_dir = mc_root / f"run_{i:04d}"
        run_dir.mkdir()
        project = run_dir / "project.json"
        project.write_text(json.dumps({"run": i, "v": 1}), encoding="utf-8")
        train = run_dir / "train_control.csv"
        train.write_text(f"sample\ns{i}\n", encoding="utf-8")
        artifacts_v1.append(ArtifactRef(path=str(project), bytes=project.stat().st_size))
        artifacts_v1.append(ArtifactRef(path=str(train), bytes=train.stat().st_size))

    record_v1 = _record(
        artifacts=artifacts_v1,
        input_sig="sig-plan-v1",
        output_sig="out-plan-v1",
    ).model_copy(
        update={
            "action_name": "validation.plan_iterations",
            "task_output": {
                "iterations": [
                    {"projectPath": str(mc_root / "run_0001" / "project.json")},
                    {"projectPath": str(mc_root / "run_0002" / "project.json")},
                ]
            },
        }
    )
    commit_artifacts_to_store(
        project_root,
        "validation.plan_iterations",
        "key-plan-v1",
        record_v1,
        output_dir=mc_root,
    )
    entry_v1 = caas_entry_dir(project_root, "validation.plan_iterations", "key-plan-v1")
    assert (entry_v1 / "run_0001" / "project.json").is_file()
    assert (entry_v1 / "run_0002" / "project.json").is_file()

    # Simulate a fresh plan under a new content key while product paths are still CAAS symlinks.
    artifacts_v2: list[ArtifactRef] = []
    for i in (1, 2):
        project = mc_root / f"run_{i:04d}" / "project.json"
        assert project.is_symlink()
        # Writers unlink the symlink then write a real file (prepare_path_for_write).
        project.unlink()
        project.write_text(json.dumps({"run": i, "v": 2}), encoding="utf-8")
        train = mc_root / f"run_{i:04d}" / "train_control.csv"
        train.unlink()
        train.write_text(f"sample\ns{i}-v2\n", encoding="utf-8")
        artifacts_v2.append(ArtifactRef(path=str(project), bytes=project.stat().st_size))
        artifacts_v2.append(ArtifactRef(path=str(train), bytes=train.stat().st_size))

    record_v2 = _record(
        artifacts=artifacts_v2,
        input_sig="sig-plan-v2",
        output_sig="out-plan-v2",
    ).model_copy(
        update={
            "action_name": "validation.plan_iterations",
            "task_output": {
                "iterations": [
                    {"projectPath": str(mc_root / "run_0001" / "project.json")},
                    {"projectPath": str(mc_root / "run_0002" / "project.json")},
                ]
            },
        }
    )
    commit_artifacts_to_store(
        project_root,
        "validation.plan_iterations",
        "key-plan-v2",
        record_v2,
        output_dir=mc_root,
    )

    entry_v2 = caas_entry_dir(project_root, "validation.plan_iterations", "key-plan-v2")
    assert (entry_v2 / "run_0001" / "project.json").is_file()
    assert (entry_v2 / "run_0002" / "project.json").is_file()
    assert json.loads((entry_v2 / "run_0001" / "project.json").read_text()) == {"run": 1, "v": 2}
    # Sibling content-key must remain intact (no steal via resolve()+move).
    assert (entry_v1 / "run_0001" / "project.json").is_file()
    assert json.loads((entry_v1 / "run_0001" / "project.json").read_text()) == {"run": 1, "v": 1}
    for i in (1, 2):
        link = mc_root / f"run_{i:04d}" / "project.json"
        assert link.is_symlink()
        assert json.loads(link.read_text(encoding="utf-8")) == {"run": i, "v": 2}


def test_plan_iterations_commit_recovers_run_layout_from_caas_symlink_paths(
    tmp_path: Path, monkeypatch
) -> None:
    """Artifact paths that already resolve into an old CAAS key must keep run_#### layout."""
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    project_root = tmp_path / "Study"
    mc_root = project_root / "monte_carlo_runs"
    mc_root.mkdir(parents=True)
    (mc_root / "queue").mkdir()

    old_entry = caas_entry_dir(project_root, "validation.plan_iterations", "old-key")
    artifacts: list[ArtifactRef] = []
    for i in (1, 2):
        blob_dir = old_entry / f"run_{i:04d}"
        blob_dir.mkdir(parents=True)
        blob = blob_dir / "project.json"
        blob.write_text(json.dumps({"run": i}), encoding="utf-8")
        logical = mc_root / f"run_{i:04d}" / "project.json"
        logical.parent.mkdir(parents=True, exist_ok=True)
        logical.symlink_to(os.path.relpath(blob, start=logical.parent))
        # Bug reproduction: collectors/planners sometimes recorded the resolved CAAS path.
        artifacts.append(ArtifactRef(path=str(blob.resolve()), bytes=blob.stat().st_size))

    record = _record(
        artifacts=artifacts,
        input_sig="sig-resolved-caas",
        output_sig="out-resolved-caas",
    ).model_copy(
        update={
            "action_name": "validation.plan_iterations",
            "task_output": {
                "iterations": [
                    {"projectPath": str((old_entry / "run_0001" / "project.json").resolve())},
                    {"projectPath": str((old_entry / "run_0002" / "project.json").resolve())},
                ]
            },
        }
    )
    commit_artifacts_to_store(
        project_root,
        "validation.plan_iterations",
        "new-key",
        record,
        output_dir=mc_root,
    )
    new_entry = caas_entry_dir(project_root, "validation.plan_iterations", "new-key")
    assert (new_entry / "run_0001" / "project.json").is_file()
    assert (new_entry / "run_0002" / "project.json").is_file()
    # Must copy, not steal, from the old content key.
    assert (old_entry / "run_0001" / "project.json").is_file()
    assert (old_entry / "run_0002" / "project.json").is_file()
