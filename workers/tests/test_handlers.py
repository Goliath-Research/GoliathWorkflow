"""Tests for capability dispatch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from methyl_worker.handlers import execute_task


def test_mark_failed_handler() -> None:
    out = execute_task(
        "sample.mark-failed",
        "sample.qc_failed",
        {"sampleId": "S1", "sampleDir": "/work/samples/S1", "reason": "alignment_qc_failed"},
    )
    assert out["status"] == "QC_FAILED"
    assert out["sampleId"] == "S1"


def test_download_requires_fastq_source_uri() -> None:
    with pytest.raises(RuntimeError, match="requires fastqSourceUri"):
        execute_task(
            "sample.download-fastq",
            "sample.download_fastq",
            {"sampleId": "S1", "sampleDir": "/tmp/S1"},
        )


def test_parabricks_idempotent_when_outputs_exist(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S1"
    sample_dir.mkdir()
    bam = sample_dir / "S1.bam"
    metrics = sample_dir / "S1.json"
    bam.write_bytes(b"BAM")
    metrics.write_text("{}")

    out = execute_task(
        "parabricks.fq2bam",
        "sample.parabricks_fq2bam",
        {
            "sampleId": "S1",
            "sampleDir": str(sample_dir),
            "referenceFasta": "/ref/genome.fa",
        },
    )
    assert out["bamPath"] == str(bam)
    assert out["metricsJson"] == str(metrics)


def test_pipeline_cli_dispatch() -> None:
    with patch("methyl_worker.actions.base.subprocess.run") as mock_run:
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "done", "stderr": ""})()
        out = execute_task(
            "methyl-mapper",
            "pipeline.mapper",
            {"tool": "MethylMapper", "project": "/cfg/project.json"},
        )
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == ["methyl-mapper", "--project", "/cfg/project.json"]
    assert out["status"] == "ok"
