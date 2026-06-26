"""Run and parse samtools flagstat for BAM alignment QC."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from ..models.config import AlignmentGuardrailsConfig

_FLAGSTAT_LINE = re.compile(
    r"^(\d+)\s+\+\s+(\d+)\s+(.+)$",
)


def parse_flagstat_text(text: str) -> Dict[str, int]:
    """Parse samtools flagstat output into named counters."""
    counts: Dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _FLAGSTAT_LINE.match(line)
        if not match:
            continue
        primary = int(match.group(1))
        secondary = int(match.group(2))
        label = match.group(3).strip().lower()
        total = primary + secondary
        if "in total" in label:
            counts["total_reads"] = total
        elif label == "secondary":
            counts["secondary_reads"] = total
        elif label == "supplementary":
            counts["supplementary_reads"] = total
        elif label == "duplicates":
            counts["duplicate_reads"] = total
        elif label.endswith("mapped"):
            counts["mapped_reads"] = total
        elif "properly paired" in label:
            counts["properly_paired_reads"] = total
        elif "read1" in label and "read2" not in label:
            counts["read1_reads"] = total
        elif "read2" in label:
            counts["read2_reads"] = total
        elif "singletons" in label:
            counts["singleton_reads"] = total
    return counts


def _build_flagstat_metrics(counts: Dict[str, int]) -> Dict[str, Any]:
    total = int(counts.get("total_reads", 0) or 0)
    properly_paired = int(counts.get("properly_paired_reads", 0) or 0)
    supplementary = int(counts.get("supplementary_reads", 0) or 0)
    mapped = int(counts.get("mapped_reads", 0) or 0)

    metrics: Dict[str, Any] = dict(counts)
    if total > 0:
        metrics["properly_paired_rate"] = round((2 * properly_paired) / total, 6)
        metrics["supplementary_rate"] = round(supplementary / total, 6)
        metrics["mapped_rate"] = round(mapped / total, 6)
    return metrics


def run_flagstat(
    sample_dir: Path,
    sample_id: str,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Run samtools flagstat on {sample_id}.bam; cache as {sample_id}.flagstat.txt.

    Returns alignment_flagstat metrics dict. Raises RuntimeError when BAM missing
    or samtools/flagstat fails.
    """
    sample_dir = Path(sample_dir)
    bam_path = sample_dir / f"{sample_id}.bam"
    cache_path = sample_dir / f"{sample_id}.flagstat.txt"

    if not bam_path.is_file():
        raise RuntimeError(f"BAM not found for flagstat: {bam_path}")

    samtools = shutil.which("samtools")
    if samtools is None:
        raise RuntimeError("samtools not found on PATH; required for alignment flagstat QC")

    if cache_path.is_file() and not force:
        bam_mtime = bam_path.stat().st_mtime
        cache_mtime = cache_path.stat().st_mtime
        if cache_mtime >= bam_mtime:
            text = cache_path.read_text(encoding="utf-8")
            return _build_flagstat_metrics(parse_flagstat_text(text))

    proc = subprocess.run(
        [samtools, "flagstat", str(bam_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"samtools flagstat failed for {bam_path}: {err}")

    text = proc.stdout or ""
    cache_path.write_text(text, encoding="utf-8")
    return _build_flagstat_metrics(parse_flagstat_text(text))


def apply_flagstat_guardrails(
    report: Dict[str, Any],
    flagstat: Optional[Dict[str, Any]],
    cfg: AlignmentGuardrailsConfig,
    *,
    error: Optional[str] = None,
) -> None:
    """Append Phase-2 flagstat guardrails when cfg.flagstat_enabled."""
    if not cfg.flagstat_enabled:
        return

    details = report.setdefault("details", {})

    def _fail_metric(key: str, normal_range: str, message: str) -> None:
        details[key] = {
            "value": None,
            "normal_range": normal_range,
            "pass": False,
            "message": message,
        }
        report["overall_pass"] = False

    if error is not None:
        if cfg.min_properly_paired_rate is not None:
            _fail_metric(
                "properly_paired_rate",
                f">= {cfg.min_properly_paired_rate}",
                error,
            )
        if cfg.max_supplementary_rate_flagstat is not None:
            _fail_metric(
                "supplementary_rate_flagstat",
                f"<= {cfg.max_supplementary_rate_flagstat}",
                error,
            )
        return

    if flagstat is None:
        return

    if cfg.min_properly_paired_rate is not None:
        rate = flagstat.get("properly_paired_rate")
        if rate is None:
            _fail_metric(
                "properly_paired_rate",
                f">= {cfg.min_properly_paired_rate}",
                "flagstat output missing properly paired count.",
            )
        else:
            passed = float(rate) >= cfg.min_properly_paired_rate
            details["properly_paired_rate"] = {
                "value": float(rate),
                "normal_range": f">= {cfg.min_properly_paired_rate}",
                "pass": passed,
                "message": (
                    "Fraction of reads in proper pairs (samtools flagstat). "
                    "Low values indicate pairing or mapping problems."
                ),
            }
            if not passed:
                report["overall_pass"] = False

    if cfg.max_supplementary_rate_flagstat is not None:
        rate = flagstat.get("supplementary_rate")
        if rate is None:
            _fail_metric(
                "supplementary_rate_flagstat",
                f"<= {cfg.max_supplementary_rate_flagstat}",
                "flagstat output missing supplementary count.",
            )
        else:
            passed = float(rate) <= cfg.max_supplementary_rate_flagstat
            details["supplementary_rate_flagstat"] = {
                "value": float(rate),
                "normal_range": f"<= {cfg.max_supplementary_rate_flagstat}",
                "pass": passed,
                "message": (
                    "Supplementary alignments as a fraction of total reads (samtools flagstat)."
                ),
            }
            if not passed:
                report["overall_pass"] = False

    if not report.get("overall_pass") and str(report.get("recommendation", "")).startswith("PASS"):
        report["recommendation"] = (
            "FAIL: Do NOT proceed. Investigate BAM pairing/supplementary alignment "
            "before methylation extraction."
        )
