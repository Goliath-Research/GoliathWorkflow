"""Tests for FOREACH iteration-bundle CAAS."""

from __future__ import annotations

from pathlib import Path

from methyl_domain.foreach_bundle import (
    commit_iteration_bundle,
    compute_iteration_bundle_key,
    read_iteration_bundle,
)
from methyl_domain.sample_content_store import (
    resolve_sample_caas_root,
    sample_caas_enabled_for_action,
    sample_caas_opt_out_reason,
)


def test_bundle_key_stable() -> None:
    kwargs = dict(
        foreach_node_key="fe",
        collection_var="items",
        iteration_index=2,
        item_payload={"a": 1},
        child_action_revisions=["pipeline.centroid:x"],
    )
    assert compute_iteration_bundle_key(**kwargs) == compute_iteration_bundle_key(**kwargs)


def test_commit_read(tmp_path: Path) -> None:
    key = compute_iteration_bundle_key(
        foreach_node_key="fe",
        collection_var="items",
        iteration_index=0,
        item_payload="x",
    )
    commit_iteration_bundle(
        tmp_path,
        key,
        foreach_node_key="fe",
        collection_var="items",
        iteration_index=0,
        item_payload="x",
    )
    assert read_iteration_bundle(tmp_path, key)["status"] == "completed"


def test_sample_opt_outs() -> None:
    assert sample_caas_opt_out_reason("sample.delete_bam") == "destructive"
    assert sample_caas_enabled_for_action("sample.download_fastq") is False


def test_sample_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("METHYL_SAMPLES_BASE", str(tmp_path))
    root = resolve_sample_caas_root({"sampleId": "S1"})
    assert root == tmp_path / "S1"
