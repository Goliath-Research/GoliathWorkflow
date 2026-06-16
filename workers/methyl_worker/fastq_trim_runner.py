"""Run fastp Read 2 front-trim for alignment QC remediation."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)


def run_fastp_trim_front2(
    *,
    sample_id: str,
    sample_dir: str | Path,
    trim_front2: int,
    input_json: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    """Trim Read 2 front bases with fastp; write *_trimmed.fastq.gz beside originals."""
    if trim_front2 < 1:
        raise RuntimeError(f"trimFront2 must be >= 1, got {trim_front2}")

    sample_path = Path(sample_dir).resolve()
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")

    r1_in = sample_path / f"{sample_id}_1.fastq.gz"
    r2_in = sample_path / f"{sample_id}_2.fastq.gz"
    if not r1_in.is_file() or not r2_in.is_file():
        raise RuntimeError(f"Expected paired FASTQs under {sample_path}: {r1_in.name}, {r2_in.name}")

    r1_out = sample_path / f"{sample_id}_1.trimmed.fastq.gz"
    r2_out = sample_path / f"{sample_id}_2.trimmed.fastq.gz"

    fastp = shutil.which("fastp")
    if fastp is None:
        raise RuntimeError("fastp not found on PATH; install via apt or conda")

    cmd = [
        fastp,
        "-i",
        str(r1_in),
        "-I",
        str(r2_in),
        "-o",
        str(r1_out),
        "-O",
        str(r2_out),
        "--trim_front2",
        str(int(trim_front2)),
        "--disable_quality_filtering",
    ]
    logger.info("Running fastp trim_front2=%s for %s", trim_front2, sample_id)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "fastp failed")
    if not r1_out.is_file() or not r2_out.is_file():
        raise RuntimeError("fastp did not produce trimmed FASTQ outputs")

    return {
        "sampleId": sample_id,
        "trimFront2": str(trim_front2),
        "trimmedR1": str(r1_out),
        "trimmedR2": str(r2_out),
        "logReason": str((input_json or {}).get("remediationReason") or ""),
    }
