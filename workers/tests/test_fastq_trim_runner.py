"""Tests for fastp trim FASTQ discovery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from methyl_worker.fastq_trim_runner import run_fastp_trim


def test_trim_discovers_noncanonical_paired_fastqs(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S_lanes"
    sample_dir.mkdir()
    r1 = sample_dir / "S_lanes_L001_R1_001.fastq.gz"
    r2 = sample_dir / "S_lanes_L001_R2_001.fastq.gz"
    r1.write_bytes(b"r1")
    r2.write_bytes(b"r2")

    def fake_run(cmd, **kwargs):
        out_r1 = Path(cmd[cmd.index("-o") + 1])
        out_r2 = Path(cmd[cmd.index("-O") + 1])
        out_r1.write_bytes(b"t1")
        out_r2.write_bytes(b"t2")
        class _P:
            returncode = 0
            stdout = ""
            stderr = ""
        return _P()

    with patch("methyl_worker.fastq_trim_runner.shutil.which", return_value="fastp"):
        with patch("methyl_worker.fastq_trim_runner.subprocess.run", side_effect=fake_run):
            out = run_fastp_trim(
                sample_id="S_lanes",
                sample_dir=sample_dir,
                input_json={"trimFront2": 5},
            )
    assert Path(out["trimmedR1"]).name == "S_lanes_1.trimmed.fastq.gz"
    assert Path(out["trimmedR2"]).is_file()


def test_trim_requires_paired_fastqs(tmp_path: Path) -> None:
    sample_dir = tmp_path / "S_empty"
    sample_dir.mkdir()
    with pytest.raises(RuntimeError, match="paired FASTQ"):
        run_fastp_trim(
            sample_id="S_empty",
            sample_dir=sample_dir,
            input_json={"trimFront2": 5},
        )
