"""CAAS integration tests for signature-based action skip/replay."""

from __future__ import annotations

import json
import os
from pathlib import Path

from methyl_worker.action_catalog import find_catalog_entry
from methyl_worker.action_execution import execution_result_from_output, validate_input
from methyl_worker.action_skip import (
    compute_action_revision,
    compute_content_key,
    compute_input_signature,
    maybe_skip_action,
    record_action_execution,
)
from methyl_worker.task_models.validation_models import StabilitySummary, ValidationStabilityOutput
from methyl_worker.task_validation import strip_runtime_input


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


def test_compute_content_key_stable() -> None:
    key_a = compute_content_key("rev", "sig")
    key_b = compute_content_key("rev", "sig")
    key_c = compute_content_key("rev", "other")
    assert key_a == key_b
    assert key_a != key_c


def test_caas_cross_instance_skip_relinks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    entry = find_catalog_entry("validation.stability")
    assert entry is not None

    project_root = tmp_path / "Study"
    mc_root = project_root / "monte_carlo_runs"
    stability_dir = mc_root / "stability"
    stability_dir.mkdir(parents=True)
    summary = stability_dir / "stability_summary.json"
    summary.write_text('{"n": 1}', encoding="utf-8")

    project = tmp_path / "configs" / "project.json"
    _write_study_project(project, tmp_path)

    input_json = {
        "projectPath": str(project),
        "monteCarloRunsRoot": str(mc_root),
        "outputDir": str(stability_dir),
        "resolvedConfig": {"n_iterations": 2, "stability_dmp_freq": 0.7},
        "hyperparamSetId": "hpset-a",
        "caasEnabled": True,
    }
    input_model = validate_input(entry, strip_runtime_input(input_json))
    output = ValidationStabilityOutput(
        status="ok",
        outputDir=str(stability_dir),
        summary=StabilitySummary(summary_json_path=str(summary), n_iterations=2),
    )
    record_action_execution(entry, input_json, input_model, execution_result_from_output(output))

    from methyl_domain.action_result import action_results_dir

    local_manifest_dir = action_results_dir(stability_dir)
    for path in local_manifest_dir.glob("*.json"):
        path.unlink()

    input_b = {**input_json, "hyperparamSetId": "hpset-b"}
    skipped = maybe_skip_action(entry, input_b)
    assert skipped is not None
    assert skipped.output.status == "skipped"
    assert summary.is_symlink()

    ledger = project_root / ".caas" / "instances" / "hpset-b.json"
    assert ledger.is_file()


def test_symlink_paths_affect_input_signature(tmp_path: Path) -> None:
    entry = find_catalog_entry("pipeline.centroid")
    assert entry is not None

    project_root = tmp_path / "Study"
    out_dir = project_root / "centroids" / "all"
    entry_dir = project_root / ".caas" / "pipeline_centroid" / "abc123"
    entry_dir.mkdir(parents=True)
    h5_store = entry_dir / "1-CG.h5"
    h5_store.write_bytes(b"data")
    out_dir.mkdir(parents=True)
    h5_link = out_dir / "1-CG.h5"
    h5_link.symlink_to(h5_store)

    from pydantic import BaseModel

    class FakeInput(BaseModel):
        outputDir: str
        centroid_h5_path: str

    # Signature computed from the symlink path.
    model_link = FakeInput(outputDir=str(out_dir), centroid_h5_path=str(h5_link))
    sig_link = compute_input_signature(
        entry,
        {"outputDir": str(out_dir), "centroid_h5_path": str(h5_link)},
        model_link,
    )

    # Signature computed from the resolved (real) target path.
    model_real = FakeInput(outputDir=str(out_dir), centroid_h5_path=str(h5_store))
    sig_real = compute_input_signature(
        entry,
        {"outputDir": str(out_dir), "centroid_h5_path": str(h5_store)},
        model_real,
    )

    # Signature computed from a *different* real file (negative control).
    other = out_dir / "1-CG-other.h5"
    other.write_bytes(b"data")
    model_other = FakeInput(outputDir=str(out_dir), centroid_h5_path=str(other))
    sig_other = compute_input_signature(
        entry,
        {"outputDir": str(out_dir), "centroid_h5_path": str(other)},
        model_other,
    )

    # _normalize_path_strings resolves symlinks, so the symlink and its target
    # produce identical signatures (cumulative signatures survive relinking)...
    assert sig_link == sig_real
    # ...while the path genuinely contributes to the signature (not dropped).
    assert sig_link != sig_other


def test_stability_signature_includes_discovery_fingerprint(tmp_path: Path) -> None:
    entry = find_catalog_entry("validation.stability")
    assert entry is not None

    project = tmp_path / "configs" / "project.json"
    _write_study_project(project, tmp_path)
    project_root = tmp_path / "Study"
    mc_root = project_root / "monte_carlo_runs"
    run = mc_root / "run_0001" / "detections" / "all" / "PCa"
    run.mkdir(parents=True)
    disc = run / "dmps-1-discovery.csv"
    disc.write_text("chromosome,position\n1,1\n", encoding="utf-8")

    input_json = {
        "projectPath": str(project),
        "monteCarloRunsRoot": str(mc_root),
        "outputDir": str(mc_root / "stability"),
        "resolvedConfig": {
            "n_iterations": 2,
            "stability_dmp_freq": 0.7,
            "dmp_modeling_mode": "raw_pool",
            "stability_featurecuts_enabled": False,
        },
    }
    input_model = validate_input(entry, strip_runtime_input(input_json))
    sig1 = compute_input_signature(entry, input_json, input_model)

    disc.write_text("chromosome,position\n1,1\n1,2\n", encoding="utf-8")
    # bump mtime
    os.utime(disc, None)
    sig2 = compute_input_signature(entry, input_json, input_model)
    assert sig1 != sig2


def test_sample_caas_commit_keeps_bam_in_sample_dir(tmp_path: Path, monkeypatch) -> None:
    """Parabricks CAAS must leave the BAM at sampleDir, not under study configs/."""
    monkeypatch.delenv("METHYL_SAMPLE_CAAS_ENABLED", raising=False)
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    monkeypatch.setenv("METHYL_SAMPLES_BASE", str(tmp_path / "samples"))

    sample_dir = tmp_path / "samples" / "S1"
    sample_dir.mkdir(parents=True)
    bam = sample_dir / "S1.bam"
    bam.write_bytes(b"BAMDATA")
    fastq = sample_dir / "S1_1.fastq.gz"
    fastq.write_bytes(b"FASTQ")

    configs = tmp_path / "projects" / "study" / "configs"
    project = configs / "project.json"
    _write_study_project(project, tmp_path)

    entry = find_catalog_entry("sample.parabricks_fq2bam")
    assert entry is not None
    input_json = {
        "tool": "ParabricksFq2Bam",
        "sampleId": "S1",
        "sampleDir": str(sample_dir),
        "projectPath": str(project),
        "caasEnabled": True,
    }
    from methyl_worker.task_models.sample_prep_models import ParabricksTaskOutput

    input_model = validate_input(entry, strip_runtime_input(input_json))
    output = ParabricksTaskOutput(
        status="ok",
        sampleId="S1",
        bamPath=str(bam),
    )
    record_action_execution(
        entry, input_json, input_model, execution_result_from_output(output)
    )

    assert bam.exists()
    assert bam.resolve().is_file()
    assert bam.read_bytes() == b"BAMDATA"
    assert ".caas" in bam.resolve().parts
    assert sample_dir.resolve() in bam.resolve().parents or bam.resolve().parent == sample_dir.resolve()
    # FASTQ in the shared sampleDir must not be stolen into the align CAAS entry.
    assert fastq.is_file() and not fastq.is_symlink()
    assert not list(configs.rglob("*.bam"))


def test_sample_caas_skip_restores_products_after_stripped_leaf(
    tmp_path: Path, monkeypatch
) -> None:
    """After harvest, skip-replay must restore BAM/tar at sampleDir from .caas blobs."""
    monkeypatch.delenv("METHYL_SAMPLE_CAAS_ENABLED", raising=False)
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    monkeypatch.setenv("METHYL_SAMPLES_BASE", str(tmp_path / "samples"))

    sample_dir = tmp_path / "samples" / "S1"
    sample_dir.mkdir(parents=True)
    bam = sample_dir / "S1.bam"
    tar = sample_dir / "S1.qc-metrics.tar"
    bam.write_bytes(b"BAMDATA")
    tar.write_bytes(b"TAR")
    (sample_dir / "S1_1.fastq.gz").write_bytes(b"FASTQ")

    configs = tmp_path / "projects" / "study" / "configs"
    project = configs / "project.json"
    _write_study_project(project, tmp_path)

    entry = find_catalog_entry("sample.parabricks_fq2bam")
    assert entry is not None
    input_json = {
        "tool": "ParabricksFq2Bam",
        "sampleId": "S1",
        "sampleDir": str(sample_dir),
        "projectPath": str(project),
        "caasEnabled": True,
    }
    from methyl_worker.task_models.sample_prep_models import ParabricksTaskOutput

    input_model = validate_input(entry, strip_runtime_input(input_json))
    output = ParabricksTaskOutput(
        status="ok",
        sampleId="S1",
        bamPath=str(bam),
        qcMetricsTar=str(tar),
    )
    record_action_execution(
        entry, input_json, input_model, execution_result_from_output(output)
    )
    blob_bam = bam.resolve()
    blob_tar = tar.resolve()
    assert ".caas" in blob_bam.parts
    bam.unlink()
    tar.unlink()

    skipped = maybe_skip_action(entry, input_json)
    assert skipped is not None
    assert skipped.output.status == "skipped"
    assert bam.is_symlink()
    assert not os.path.isabs(os.readlink(bam))
    assert bam.read_bytes() == b"BAMDATA"
    assert tar.is_symlink()
    assert tar.read_bytes() == b"TAR"
    assert blob_bam.is_file() and not blob_bam.is_symlink()
    assert blob_tar.is_file() and not blob_tar.is_symlink()


def test_sample_caas_skip_restores_arm_leaf_products(tmp_path: Path, monkeypatch) -> None:
    """CAAS at sample identity root; skip restores products on the arm sampleDir."""
    monkeypatch.delenv("METHYL_SAMPLE_CAAS_ENABLED", raising=False)
    monkeypatch.setenv("METHYL_CAAS_ENABLED", "true")
    monkeypatch.setenv("METHYL_SAMPLES_BASE", str(tmp_path / "samples"))

    sample_root = tmp_path / "samples" / "S1"
    arm = sample_root / "align.linear.parabricks"
    arm.mkdir(parents=True)
    bam = arm / "S1.bam"
    tar = arm / "S1.qc-metrics.tar"
    bam.write_bytes(b"BAMDATA")
    tar.write_bytes(b"TAR")
    (arm / "S1_1.fastq.gz").write_bytes(b"FASTQ")

    configs = tmp_path / "projects" / "study" / "configs"
    project = configs / "project.json"
    _write_study_project(project, tmp_path)

    entry = find_catalog_entry("sample.parabricks_fq2bam")
    assert entry is not None
    input_json = {
        "tool": "ParabricksFq2Bam",
        "sampleId": "S1",
        "sampleDir": str(arm),
        "projectPath": str(project),
        "caasEnabled": True,
    }
    from methyl_worker.task_models.sample_prep_models import ParabricksTaskOutput

    input_model = validate_input(entry, strip_runtime_input(input_json))
    output = ParabricksTaskOutput(
        status="ok",
        sampleId="S1",
        bamPath=str(bam),
        qcMetricsTar=str(tar),
    )
    record_action_execution(
        entry, input_json, input_model, execution_result_from_output(output)
    )
    blob_bam = bam.resolve()
    assert (sample_root / ".caas") in blob_bam.parents
    assert "align.linear.parabricks" not in blob_bam.parts
    bam.unlink()
    tar.unlink()

    skipped = maybe_skip_action(entry, input_json)
    assert skipped is not None
    assert bam.is_symlink()
    assert bam.read_bytes() == b"BAMDATA"
    assert tar.is_symlink()
    assert tar.read_bytes() == b"TAR"
    assert not (sample_root / "S1.bam").exists()
    assert blob_bam.is_file() and not blob_bam.is_symlink()
    assert not list(configs.rglob("*.bam"))
