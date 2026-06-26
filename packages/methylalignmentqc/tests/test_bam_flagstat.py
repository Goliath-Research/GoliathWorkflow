"""Tests for samtools flagstat parsing and guardrails."""

from __future__ import annotations

from methyl_alignment_qc.core.bam_flagstat import (
    apply_flagstat_guardrails,
    parse_flagstat_text,
)
from methyl_alignment_qc.models.config import AlignmentGuardrailsConfig

FLAGSTAT_FIXTURE = """1000 + 0 in total (QC-passed reads + QC-failed reads)
50 + 0 secondary
10 + 0 supplementary
100 + 0 duplicates
950 + 0 mapped
1000 + 0 paired in sequencing
900 + 0 read1
900 + 0 read2
850 + 0 properly paired (N-BAIMPROPER)
50 + 0 with itself and mate mapped
0 + 0 singletons (itself mapped; mate unmapped)
0 + 0 with mate mapped to a different chr
0 + 0 with mate mapped to a different chr (mapQ>=5)
"""


def test_parse_flagstat_text() -> None:
    counts = parse_flagstat_text(FLAGSTAT_FIXTURE)
    assert counts["total_reads"] == 1000
    assert counts["properly_paired_reads"] == 850
    assert counts["supplementary_reads"] == 10


def test_apply_flagstat_guardrails_pass() -> None:
    metrics = {
        "properly_paired_rate": 0.95,
        "supplementary_rate": 0.01,
    }
    report = {"overall_pass": True, "recommendation": "PASS", "details": {}}
    cfg = AlignmentGuardrailsConfig(
        enabled=True,
        flagstat_enabled=True,
        min_properly_paired_rate=0.90,
        max_supplementary_rate_flagstat=0.02,
    )
    apply_flagstat_guardrails(report, metrics, cfg)
    assert report["overall_pass"] is True
    assert report["details"]["properly_paired_rate"]["pass"] is True


def test_apply_flagstat_guardrails_fail_on_error() -> None:
    report = {"overall_pass": True, "recommendation": "PASS", "details": {}}
    cfg = AlignmentGuardrailsConfig(
        enabled=True,
        flagstat_enabled=True,
        min_properly_paired_rate=0.90,
    )
    apply_flagstat_guardrails(report, None, cfg, error="samtools not found")
    assert report["overall_pass"] is False
