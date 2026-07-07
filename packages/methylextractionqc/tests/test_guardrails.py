"""Tests for extraction QC guardrails."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from methyl_extraction_qc.core.writer import process_sample_extraction_qc
from methyl_extraction_qc.guardrails import evaluate_guardrails
from methyl_extraction_qc.models.config import ExtractionQCConfig, ExtractionQCGuardrailConfig


def _manifest_fixture(
    *,
    cpg_cov: float = 15.0,
    chh: float = 0.005,
    chg: float = 0.004,
    retention_rate: float | None = 0.85,
) -> dict:
    per_chromosome = {}
    for chrom in ["1", "2", "21", "X"]:
        per_chromosome[chrom] = {
            "CG": {
                "num_positions": 1000,
                "methylation_level": 0.6,
                "mean_coverage": 12.0 if chrom != "21" else 11.0,
            }
        }
    manifest = {
        "metadata": {
            "schema_name": "methylextractor.extraction_manifest",
            "schema_version": "1.0.0",
            "sample_id": "S1",
            "contexts_extracted": ["CG", "CHG", "CHH"],
        },
        "summary": {
            "cpg_weighted_mean_coverage": cpg_cov,
            "cpg_methylation_level": 0.62,
            "chh_methylation_level": chh,
            "chg_methylation_level": chg,
        },
        "per_chromosome": per_chromosome,
    }
    if retention_rate is not None:
        reads_seen = 1_000_000
        reads_used = round(reads_seen * retention_rate)
        manifest["read_filtering"] = {
            "reads_seen": reads_seen,
            "reads_used": reads_used,
            "read_retention_rate": retention_rate,
        }
    return manifest


def test_evaluate_guardrails_passes_good_manifest() -> None:
    report = evaluate_guardrails(
        _manifest_fixture(),
        config=ExtractionQCGuardrailConfig(),
        expected_chromosomes=["1", "2", "21", "X"],
    )
    assert report["overall_pass"] is True
    assert report["metrics"]["cpg_weighted_mean_coverage"]["pass"] is True


def test_evaluate_guardrails_fails_low_coverage() -> None:
    report = evaluate_guardrails(
        _manifest_fixture(cpg_cov=4.0),
        config=ExtractionQCGuardrailConfig(),
        expected_chromosomes=["1", "2", "21", "X"],
    )
    assert report["overall_pass"] is False
    assert report["metrics"]["cpg_weighted_mean_coverage"]["pass"] is False


def test_evaluate_guardrails_fails_high_chh() -> None:
    report = evaluate_guardrails(
        _manifest_fixture(chh=0.05),
        config=ExtractionQCGuardrailConfig(),
        expected_chromosomes=["1", "2", "21", "X"],
    )
    assert report["overall_pass"] is False
    assert report["metrics"]["chh_methylation_level"]["pass"] is False


def test_evaluate_guardrails_read_discard_passes_normal_retention() -> None:
    report = evaluate_guardrails(
        _manifest_fixture(retention_rate=0.85),
        config=ExtractionQCGuardrailConfig(),
        expected_chromosomes=["1", "2", "21", "X"],
    )
    metric = report["metrics"]["read_discard_fraction"]
    assert metric["pass"] is True
    assert metric["value"]["discard_fraction"] == pytest.approx(0.15)


def test_evaluate_guardrails_fails_high_discard_fraction() -> None:
    report = evaluate_guardrails(
        _manifest_fixture(retention_rate=0.05),
        config=ExtractionQCGuardrailConfig(),
        expected_chromosomes=["1", "2", "21", "X"],
    )
    assert report["overall_pass"] is False
    metric = report["metrics"]["read_discard_fraction"]
    assert metric["pass"] is False
    assert metric["value"]["discard_fraction"] == pytest.approx(0.95)


def test_evaluate_guardrails_read_discard_honors_config_threshold() -> None:
    report = evaluate_guardrails(
        _manifest_fixture(retention_rate=0.6),
        config=ExtractionQCGuardrailConfig(max_discard_fraction=0.3),
        expected_chromosomes=["1", "2", "21", "X"],
    )
    assert report["metrics"]["read_discard_fraction"]["pass"] is False


def test_evaluate_guardrails_read_discard_skipped_when_absent() -> None:
    report = evaluate_guardrails(
        _manifest_fixture(retention_rate=None),
        config=ExtractionQCGuardrailConfig(),
        expected_chromosomes=["1", "2", "21", "X"],
    )
    metric = report["metrics"]["read_discard_fraction"]
    assert metric["pass"] is True
    assert metric["value"] is None


def test_evaluate_guardrails_read_discard_from_counts_without_rate() -> None:
    manifest = _manifest_fixture(retention_rate=None)
    manifest["read_filtering"] = {"reads_seen": 100, "reads_used": 40}
    report = evaluate_guardrails(
        manifest,
        config=ExtractionQCGuardrailConfig(max_discard_fraction=0.5),
        expected_chromosomes=["1", "2", "21", "X"],
    )
    metric = report["metrics"]["read_discard_fraction"]
    assert metric["pass"] is False
    assert metric["value"]["discard_fraction"] == pytest.approx(0.6)


def test_process_sample_extraction_qc_writes_json(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    manifest = _manifest_fixture()
    (sample_dir / "S1.extraction_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    output = process_sample_extraction_qc(
        sample_dir,
        "S1",
        config=ExtractionQCConfig(expected_chromosomes=["1", "2", "21", "X"]),
    )
    assert output.name == "S1.extraction_qc.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["guardrails"]["overall_pass"] is True
    assert payload["metadata"]["schema_name"] == "methylpipeline.extraction_qc"


def test_process_sample_extraction_qc_requires_manifest(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        process_sample_extraction_qc(sample_dir, "S1")
