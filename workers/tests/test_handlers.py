"""Tests for capability dispatch."""

from __future__ import annotations

import os
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


def test_stub_external_requires_flag() -> None:
    with patch.dict(os.environ, {"WORKER_STUB_EXTERNAL": ""}, clear=False):
        with pytest.raises(RuntimeError, match="No local handler"):
            execute_task(
                "sample.download-fastq",
                "sample.download_fastq",
                {"sampleId": "S1", "sampleDir": "/tmp/S1"},
            )


def test_stub_external_dry_run() -> None:
    with patch.dict(os.environ, {"WORKER_STUB_EXTERNAL": "1"}, clear=False):
        out = execute_task(
            "parabricks.fq2bam",
            "sample.parabricks_fq2bam",
            {"sampleId": "S1", "sampleDir": "/work/samples/S1"},
        )
    assert out["bamPath"] == "/work/samples/S1/S1.bam"


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
