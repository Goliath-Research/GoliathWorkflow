#!/usr/bin/env python3
"""
WGBS Parabricks JSON QC Guardrail Checker (Updated with Pre-Adapter Artifacts)

Enforces sequencing + alignment + deamination/artifact guardrails for WGBS.
Run this BEFORE methylation extraction with your MethylDackel fork.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

def load_parabricks_json(json_path: str) -> Dict[str, Any]:
    """Load the Parabricks metrics JSON."""
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def _make_guardrail_metric(
    *,
    value: float,
    normal_range: str,
    passed: bool,
    message: str,
) -> Dict[str, Any]:
    """Build one metric payload with user-facing guidance."""
    return {
        "value": value,
        "normal_range": normal_range,
        "pass": passed,
        "message": message,
    }


def _build_wgbs_guardrail_report(
    data: Dict[str, Any],
    q30_threshold: float = 85.0,
) -> Dict[str, Any]:
    """Build guardrail report from already-loaded Parabricks JSON payload."""
    qy = data["quality_yield"]
    mq = data["mean_quality_by_cycle"]["mean_quality"]
    gc = data["gc_bias_summary"]
    ins = data["insert_size_metrics"]
    pre = data.get("pre_adapter_summaries", {})

    # Core sequencing metrics
    pf_pct = (qy["pf_reads"] / qy["total_reads"]) * 100
    q30_pct = (qy["pf_q30_bases"] / qy["pf_bases"]) * 100
    mean_qual = sum(mq) / len(mq)
    min_qual_post20 = min(mq[20:]) if len(mq) > 20 else min(mq)

    # GC bias
    at_dropout = gc["at_dropout"]
    gc_dropout = gc["gc_dropout"]

    # Insert size
    median_insert = ins["median_insert_size"]

    # Pre-adapter artifact metrics (Deamination & OxoG)
    artifact_names: List[str] = pre.get("ARTIFACT_NAME", [])
    qscores: List[int] = pre.get("TOTAL_QSCORE", [])

    deam_idx = next((i for i, name in enumerate(artifact_names) if name == "Deamination"), None)
    oxog_idx = next((i for i, name in enumerate(artifact_names) if name == "OxoG"), None)

    deam_score = qscores[deam_idx] if deam_idx is not None else 100
    oxog_score = qscores[oxog_idx] if oxog_idx is not None else 100

    # Compile results with clear thresholds
    pf_pass = pf_pct >= 90.0
    q30_pass = q30_pct >= q30_threshold
    mean_qual_pass = mean_qual >= 35.0
    min_qual_post20_pass = min_qual_post20 >= 30.0
    at_dropout_pass = at_dropout < 3.0
    gc_dropout_pass = gc_dropout < 5.0
    median_insert_pass = 150 <= median_insert <= 300
    deam_pass = deam_score <= 30
    oxog_pass = oxog_score >= 20

    results = {
        "pf_percent": _make_guardrail_metric(
            value=round(pf_pct, 2),
            normal_range=">= 90",
            passed=pf_pass,
            message="Percentage of reads passing Illumina PF filtering. Low values can indicate run-level quality issues.",
        ),
        "q30_percent": _make_guardrail_metric(
            value=round(q30_pct, 2),
            normal_range=f">= {q30_threshold}",
            passed=q30_pass,
            message="Percentage of PF bases with Q30 or better. This reflects confidence in base calls for downstream analysis.",
        ),
        "mean_quality": _make_guardrail_metric(
            value=round(mean_qual, 2),
            normal_range=">= 35",
            passed=mean_qual_pass,
            message="Average Phred quality across cycles. Lower values indicate noisier reads and weaker sequencing confidence.",
        ),
        "min_quality_post20": _make_guardrail_metric(
            value=round(min_qual_post20, 2),
            normal_range=">= 30",
            passed=min_qual_post20_pass,
            message="Minimum quality after cycle 20. Captures late-cycle degradation that can hurt alignment and methylation calls.",
        ),
        "at_dropout": _make_guardrail_metric(
            value=round(at_dropout, 3),
            normal_range="< 3.0",
            passed=at_dropout_pass,
            message="AT-rich region dropout. High values suggest uneven representation of AT-rich genomic content.",
        ),
        "gc_dropout": _make_guardrail_metric(
            value=round(gc_dropout, 3),
            normal_range="< 5.0",
            passed=gc_dropout_pass,
            message="GC-rich region dropout. High values suggest uneven representation of GC-rich genomic content.",
        ),
        "median_insert_bp": _make_guardrail_metric(
            value=median_insert,
            normal_range="150-300",
            passed=median_insert_pass,
            message="Median insert size (bp). Out-of-range values can indicate library preparation or fragmentation issues.",
        ),
        "deamination_qscore": _make_guardrail_metric(
            value=deam_score,
            normal_range="<= 30 (ideally <= 20)",
            passed=deam_pass,
            message="Parabricks deamination qscore. In WGBS, lower scores are expected and reflect bisulfite conversion signal.",
        ),
        "oxog_qscore": _make_guardrail_metric(
            value=oxog_score,
            normal_range=">= 20",
            passed=oxog_pass,
            message="Parabricks OxoG qscore. Lower values indicate higher oxidative G>T damage risk.",
        ),
    }

    overall_pass = all(r["pass"] for r in results.values())

    return {
        "sample_id": data.get("sample_id", "unknown"),
        "overall_pass": overall_pass,
        "details": results,
        "recommendation": (
            "PASS: Safe to proceed to methylation extraction with your MethylDackel fork."
            if overall_pass
            else "FAIL: Do NOT proceed. Investigate library prep, sequencing, or bisulfite conversion."
        ),
        "next_steps": (
            "Run MethylExtractor. "
            "Still verify quantitative conversion rate with lambda spike-in (≥99%) or non-CpG methylation (≤1–2%)."
        ),
    }


def _print_wgbs_guardrail_report(report: Dict[str, Any]) -> None:
    """Pretty print WGBS guardrail report."""
    sample_id = report.get("sample_id", "unknown")
    results = report.get("details", {})
    overall_pass = report.get("overall_pass", False)
    print(f"WGBS Parabricks QC Guardrail Report – Sample: {sample_id}")
    print("=" * 80)
    for metric, res in results.items():
        status = "PASS" if res["pass"] else "FAIL"
        print(f"{metric:22} {res['value']:>8}   {res['normal_range']:>15}   {status}")
        print(f"   - {res['message']}")
    print("=" * 80)
    print(report["recommendation"])
    print(f"Overall QC Status: {'PASS' if overall_pass else 'FAIL'}")
    print("\nNext steps:", report["next_steps"])


def check_wgbs_guardrails(
    json_path: str,
    q30_threshold: float = 85.0,
    print_report: bool = True,
) -> Dict[str, Any]:
    """
    Run all guardrails and return a detailed report.
    q30_threshold: 85.0 (strict) or 80.0 (relaxed) for % Q30 bases.
    """
    data = load_parabricks_json(json_path)
    report = _build_wgbs_guardrail_report(data, q30_threshold=q30_threshold)
    if print_report:
        _print_wgbs_guardrail_report(report)
    return report


def write_guardrails_to_json(
    json_path: str,
    guardrail_report: Dict[str, Any],
    output_path: Optional[str] = None,
) -> Path:
    """Write guardrail report into JSON under key `guardrails`."""
    source_path = Path(json_path)
    target_path = Path(output_path) if output_path else source_path
    data = load_parabricks_json(str(source_path))
    data["guardrails"] = guardrail_report
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return target_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate WGBS Parabricks guardrails and store them in JSON.",
    )
    parser.add_argument("json_path", help="Path to Parabricks metrics JSON file")
    parser.add_argument(
        "--q30-threshold",
        type=float,
        default=85.0,
        help="Threshold for q30_percent guardrail (default: 85.0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional output JSON path. If omitted, update input file in place.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    json_file = args.json_path
    if not Path(json_file).is_file():
        print(f"Error: File not found → {json_file}")
        sys.exit(1)

    report = check_wgbs_guardrails(json_file, q30_threshold=args.q30_threshold)
    written_path = write_guardrails_to_json(json_file, report, output_path=args.output)
    print(f"\nGuardrails written to: {written_path}")