"""Tests for sample_prep_planner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from methyl_validation.sample_prep_planner import plan_sample_prep_context


def _write_project(tmp_path: Path, *, samples_base: str = "/work/samples") -> Path:
    project = {
        "project_name": "test_prep",
        "output_base": str(tmp_path / "out"),
        "samples_base_path": samples_base,
        "chromosomes": ["21"],
        "contexts": ["CG"],
        "controls": {
            "label": "healthy",
            "groups": [{"label": "all", "sample_paths": []}],
        },
        "diseases": {
            "label": "cancer",
            "groups": [{"label": "PCa", "sample_paths": []}],
        },
        "step_config": {
            "alignment_qc": {
                "genome_fasta": "/work/genomes/ref.fa",
            }
        },
    }
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project), encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[str]) -> None:
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_explicit_samples_with_s3_template(tmp_path: Path) -> None:
    project_path = _write_project(tmp_path)
    ctx = plan_sample_prep_context(
        {
            "projectPath": str(project_path),
            "samples": [{"sampleId": "S1"}, {"sampleId": "S2"}],
            "fastqBaseUri": "s3://bucket/prefix/",
        }
    )
    assert ctx["primaryAnalyte"] == "buffy_coat"
    assert ctx["isCfdna"] is False
    assert len(ctx["samples"]) == 2
    s1 = ctx["samples"][0]
    assert s1["sampleId"] == "S1"
    assert s1["fastqSourceUri"] == "s3://bucket/prefix/S1/"
    assert s1["sampleDir"].endswith("/S1")


def test_csv_plus_fastq_base_uri(tmp_path: Path) -> None:
    samples_base = tmp_path / "samples"
    samples_base.mkdir()
    csv = tmp_path / "cohort.csv"
    _write_csv(csv, ["alpha", "beta"])
    project_path = _write_project(tmp_path, samples_base=str(samples_base))

    ctx = plan_sample_prep_context(
        {
            "projectPath": str(project_path),
            "sampleCsv": str(csv),
            "fastqBaseUri": "az://container/plasma/",
        }
    )
    assert len(ctx["samples"]) == 2
    ids = {s["sampleId"] for s in ctx["samples"]}
    assert ids == {"alpha", "beta"}
    assert ctx["samples"][0]["fastqSourceUri"].startswith("az://container/plasma/")


def test_csv_entry_with_file_uri(tmp_path: Path) -> None:
    samples_base = tmp_path / "samples"
    samples_base.mkdir()
    csv = tmp_path / "cohort.csv"
    _write_csv(csv, ["file:///data/fastq/S99/"])
    project_path = _write_project(tmp_path, samples_base=str(samples_base))

    ctx = plan_sample_prep_context(
        {
            "projectPath": str(project_path),
            "sampleCsv": str(csv),
        }
    )
    assert len(ctx["samples"]) == 1
    assert ctx["samples"][0]["fastqSourceUri"].startswith("file:///data/fastq/S99")


def test_use_project_samples(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    healthy = data / "healthy.csv"
    pca = data / "pca.csv"
    _write_csv(healthy, ["H1"])
    _write_csv(pca, ["P1"])

    project = {
        "project_name": "cohort",
        "output_base": str(tmp_path / "out"),
        "samples_base_path": str(tmp_path / "samples"),
        "chromosomes": ["21"],
        "controls": {
            "label": "healthy",
            "groups": [{"label": "all", "sample_paths": [str(healthy)]}],
        },
        "diseases": {
            "label": "cancer",
            "groups": [{"label": "PCa", "sample_paths": [str(pca)]}],
        },
        "step_config": {"alignment_qc": {"genome_fasta": "/work/ref.fa"}},
    }
    project_path = tmp_path / "project.json"
    project_path.write_text(json.dumps(project), encoding="utf-8")

    ctx = plan_sample_prep_context(
        {
            "projectPath": str(project_path),
            "useProjectSamples": True,
            "fastqBaseUri": "s3://b/p/",
        }
    )
    assert {s["sampleId"] for s in ctx["samples"]} == {"H1", "P1"}


def test_dedupe_by_sample_id(tmp_path: Path) -> None:
    project_path = _write_project(tmp_path)
    ctx = plan_sample_prep_context(
        {
            "projectPath": str(project_path),
            "samples": [
                {"sampleId": "S1", "fastqSourceUri": "s3://b/x/S1/"},
                {"sampleId": "S1", "fastqSourceUri": "s3://b/y/S1/"},
            ],
        }
    )
    assert len(ctx["samples"]) == 1


def test_missing_fastq_base_uri_raises(tmp_path: Path) -> None:
    samples_base = tmp_path / "samples"
    samples_base.mkdir()
    csv = tmp_path / "cohort.csv"
    _write_csv(csv, ["local_sample"])
    project_path = _write_project(tmp_path, samples_base=str(samples_base))

    with pytest.raises(ValueError, match="fastqBaseUri"):
        plan_sample_prep_context(
            {
                "projectPath": str(project_path),
                "sampleCsv": str(csv),
            }
        )


def test_cfdna_primary_analyte(tmp_path: Path) -> None:
    project = {
        "project_name": "plasma",
        "output_base": str(tmp_path / "out"),
        "samples_base_path": "/work/samples",
        "chromosomes": ["21"],
        "controls": {
            "label": "healthy",
            "groups": [{"label": "all", "sample_paths": []}],
        },
        "diseases": {
            "label": "cancer",
            "groups": [{"label": "PCa", "sample_paths": []}],
        },
        "step_config": {
            "alignment_qc": {"genome_fasta": "/work/ref.fa"},
            "validation": {"regulatory": {"primary_analyte": "cfdna"}},
        },
    }
    project_path = tmp_path / "project.json"
    project_path.write_text(json.dumps(project), encoding="utf-8")

    ctx = plan_sample_prep_context(
        {
            "projectPath": str(project_path),
            "samples": [{"sampleId": "S1", "fastqSourceUri": "s3://b/S1/"}],
        }
    )
    assert ctx["primaryAnalyte"] == "cfdna"
    assert ctx["isCfdna"] is True
