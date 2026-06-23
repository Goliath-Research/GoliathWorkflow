"""Run fastp read-end trim for alignment QC remediation."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)


def _resolve_trim_values(input_json: Optional[Mapping[str, Any]]) -> Dict[str, int]:
    data = dict(input_json or {})
    trim_front1 = int(data.get("trimFront1") or data.get("trim_front1") or 0)
    trim_tail1 = int(data.get("trimTail1") or data.get("trim_tail1") or 0)
    trim_front2 = int(data.get("trimFront2") or data.get("trim_front2") or 0)
    trim_tail2 = int(data.get("trimTail2") or data.get("trim_tail2") or 0)

    screening = data.get("screening") or {}
    if isinstance(screening, dict):
        trim_front1 = trim_front1 or int(screening.get("trim_front1") or 0)
        trim_tail1 = trim_tail1 or int(screening.get("trim_tail1") or 0)
        trim_front2 = trim_front2 or int(screening.get("trim_front2") or 0)
        trim_tail2 = trim_tail2 or int(screening.get("trim_tail2") or 0)

    return {
        "trim_front1": max(0, trim_front1),
        "trim_tail1": max(0, trim_tail1),
        "trim_front2": max(0, trim_front2),
        "trim_tail2": max(0, trim_tail2),
    }


def run_fastp_trim(
    *,
    sample_id: str,
    sample_dir: str | Path,
    input_json: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    """Trim Read 1/2 start or end bases with fastp; write *_trimmed.fastq.gz beside originals."""
    trims = _resolve_trim_values(input_json)
    if not any(trims.values()):
        raise RuntimeError("sample.trim_fastq requires at least one trimFront/Tail value")

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
        "--disable_quality_filtering",
    ]
    if trims["trim_front1"]:
        cmd.extend(["--trim_front1", str(trims["trim_front1"])])
    if trims["trim_tail1"]:
        cmd.extend(["--trim_tail1", str(trims["trim_tail1"])])
    if trims["trim_front2"]:
        cmd.extend(["--trim_front2", str(trims["trim_front2"])])
    if trims["trim_tail2"]:
        cmd.extend(["--trim_tail2", str(trims["trim_tail2"])])

    logger.info("Running fastp trim for %s: %s", sample_id, trims)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "fastp failed")
    if not r1_out.is_file() or not r2_out.is_file():
        raise RuntimeError("fastp did not produce trimmed FASTQ outputs")

    return {
        "sampleId": sample_id,
        "trimFront1": str(trims["trim_front1"]),
        "trimTail1": str(trims["trim_tail1"]),
        "trimFront2": str(trims["trim_front2"]),
        "trimTail2": str(trims["trim_tail2"]),
        "trimmedR1": str(r1_out),
        "trimmedR2": str(r2_out),
        "logReason": str((input_json or {}).get("remediationReason") or ""),
    }


def run_fastp_trim_front2(
    *,
    sample_id: str,
    sample_dir: str | Path,
    trim_front2: int,
    input_json: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    """Legacy wrapper: Read 2 front trim only."""
    merged = dict(input_json or {})
    merged["trimFront2"] = trim_front2
    return run_fastp_trim(sample_id=sample_id, sample_dir=sample_dir, input_json=merged)
