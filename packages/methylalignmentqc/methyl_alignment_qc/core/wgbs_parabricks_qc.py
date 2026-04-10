#!/usr/bin/env python3
"""
WGBS Parabricks JSON QC Guardrail Checker (Updated with Pre-Adapter Artifacts)

Enforces sequencing + alignment + deamination/artifact guardrails for WGBS.
Run this BEFORE methylation extraction with your MethylDackel fork.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List

def load_parabricks_json(json_path: str) -> Dict[str, Any]:
    """Load the Parabricks metrics JSON."""
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)

def check_wgbs_guardrails(json_path: str, q30_threshold: float = 85.0) -> Dict[str, Any]:
    """
    Run all guardrails and return a detailed report.
    q30_threshold: 85.0 (strict) or 80.0 (relaxed) for % Q30 bases.
    """
    data = load_parabricks_json(json_path)
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
    results = {
        "pf_percent": {
            "value": round(pf_pct, 2),
            "threshold": ">= 90",
            "pass": pf_pct >= 90.0,
            "note": "Percentage of reads passing Illumina filter"
        },
        "q30_percent": {
            "value": round(q30_pct, 2),
            "threshold": f">= {q30_threshold}",
            "pass": q30_pct >= q30_threshold,
            "note": "Percentage of bases >= Q30 (after filter)"
        },
        "mean_quality": {
            "value": round(mean_qual, 2),
            "threshold": ">= 35",
            "pass": mean_qual >= 35.0,
            "note": "Average Phred score across all cycles"
        },
        "min_quality_post20": {
            "value": round(min_qual_post20, 2),
            "threshold": ">= 30",
            "pass": min_qual_post20 >= 30.0,
            "note": "Worst quality after cycle 20"
        },
        "at_dropout": {
            "value": round(at_dropout, 3),
            "threshold": "< 3.0",
            "pass": at_dropout < 3.0,
            "note": "AT-rich region dropout"
        },
        "gc_dropout": {
            "value": round(gc_dropout, 3),
            "threshold": "< 5.0",
            "pass": gc_dropout < 5.0,
            "note": "GC-rich region dropout"
        },
        "median_insert_bp": {
            "value": median_insert,
            "threshold": "150–300",
            "pass": 150 <= median_insert <= 300,
            "note": "Median insert size (typical for WGBS)"
        },
        "deamination_qscore": {
            "value": deam_score,
            "threshold": "≤ 30 (ideally ≤ 20)",
            "pass": deam_score <= 30,
            "note": "Lower = stronger bisulfite deamination (EXPECTED and GOOD for WGBS)"
        },
        "oxog_qscore": {
            "value": oxog_score,
            "threshold": ">= 20",
            "pass": oxog_score >= 20,
            "note": "Lower = more oxidative (G→T) damage"
        },
    }

    overall_pass = all(r["pass"] for r in results.values())

    report = {
        "sample_id": data.get("sample_id", "unknown"),
        "overall_pass": overall_pass,
        "details": results,
        "recommendation": (
            "✅ PASS → Safe to proceed to methylation extraction with your MethylDackel fork."
            if overall_pass
            else "❌ FAIL → Do NOT proceed. Investigate library prep, sequencing, or bisulfite conversion."
        ),
        "next_steps": (
            "Run MethylExtractor. "
            "Still verify quantitative conversion rate with lambda spike-in (≥99%) or non-CpG methylation (≤1–2%)."
        )
    }

    # Pretty print report
    print(f"WGBS Parabricks QC Guardrail Report – Sample: {report['sample_id']}")
    print("=" * 80)
    for metric, res in results.items():
        status = "✅ PASS" if res["pass"] else "❌ FAIL"
        print(f"{metric:22} {res['value']:>8}   {res['threshold']:>15}   {status}")
        if "note" in res:
            print(f"   └─ {res['note']}")
    print("=" * 80)
    print(report["recommendation"])
    print(f"Overall QC Status: {'✅ PASS' if overall_pass else '❌ FAIL'}")
    print("\nNext steps:", report["next_steps"])

    return report


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python wgbs_parabricks_qc.py <path_to_parabricks_metrics.json>")
        print("Example: python wgbs_parabricks_qc.py 1401-042825-50082.json")
        sys.exit(1)

    json_file = sys.argv[1]
    if not Path(json_file).is_file():
        print(f"Error: File not found → {json_file}")
        sys.exit(1)

    check_wgbs_guardrails(json_file)