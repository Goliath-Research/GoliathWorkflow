"""Tests for sample_prep_log JSONL append helper."""

from __future__ import annotations

import json
from pathlib import Path

from methyl_worker.sample_prep_log import append_sample_prep_log


def test_append_sample_prep_log_preserves_prior_lines(tmp_path: Path):
    sample_dir = tmp_path / "sampleX"
    sample_dir.mkdir()
    append_sample_prep_log(
        sample_dir,
        sample_id="sampleX",
        action="sample.trim_fastq",
        capability="sample.trim-fastq",
        reason="trim test",
        inputs={"trimFront2": 5},
        outputs={"trimmedR2": "x"},
    )
    append_sample_prep_log(
        sample_dir,
        sample_id="sampleX",
        action="sample.methyl_qc",
        capability="methyl-qc",
        attempt=2,
        reason="retry after trim",
    )
    log_path = sample_dir / "sampleX.sample_prep_log.jsonl"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["action"] == "sample.trim_fastq"
    assert second["attempt"] == 2
