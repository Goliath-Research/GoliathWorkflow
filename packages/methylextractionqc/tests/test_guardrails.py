"""Tests for extraction QC guardrails."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from methyl_extraction_qc.core.writer import process_sample_extraction_qc
from methyl_extraction_qc.guardrails import evaluate_guardrails
from methyl_extraction_qc.models.config import ExtractionQCConfig, ExtractionQCGuardrailConfig


def _manifest_fixture(*, cpg_cov: float = 15.0, chh: float = 0.005, chg: float = 0.004) -> dict:
    per_chromosome = {}
    for chrom in ["1", "2", "21", "X"]:
        per_chromosome[chrom] = {
            "CG": {
                "num_positions": 1000,
                "methylation_level": 0.6,
                "mean_coverage": 12.0 if chrom != "21" else 11.0,
            }
        }
    return {
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
