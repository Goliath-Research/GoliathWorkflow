"""Tests for V1 -> V2 AlignmentQC JSON conversion."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from methyl_alignment_qc.models.sample_qc_v2 import ExportedSampleQCV2Payload
from methyl_alignment_qc.utils.v1_to_v2_migration import (
    convert_file,
    is_v2_alignment_qc_payload,
    v1_dict_to_v2_dict,
)


def _load_writer_fixtures():
    path = Path(__file__).resolve().parent / "test_writer_guardrails.py"
    spec = importlib.util.spec_from_file_location("_writer_guardrails_fixtures", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_wg = _load_writer_fixtures()
_dedup_metrics_fixture = _wg._dedup_metrics_fixture
_parabricks_json_fixture = _wg._parabricks_json_fixture


def _minimal_v1_dict() -> dict:
    """Minimal valid ExportedSampleQCPayload as dict."""
    return {
        "sample_id": "s1",
        "quality_yield": {
            "total_reads": 1000,
            "pf_reads": 950,
            "total_bases": 120000,
            "pf_bases": 100000,
            "q20_bases": 110000,
            "pf_q20_bases": 98000,
            "q30_bases": 95000,
            "pf_q30_bases": 90000,
            "q20_equivalent_yield": 200000,
            "pf_q20_equivalent_yield": 190000,
        },
        "mean_quality_by_cycle": {"cycle": [1, 2], "mean_quality": [38.0, 37.0]},
        "quality_score_distribution": {"Q": [20, 30], "COUNT_OF_Q": [100, 90]},
        "base_distribution_by_cycle": {
            "cycle": [1],
            "PCT_A": [25.0],
            "PCT_C": [25.0],
            "PCT_G": [25.0],
            "PCT_T": [24.9],
            "PCT_N": [0.1],
        },
        "gc_bias_summary": {"at_dropout": 1.0, "gc_dropout": 2.0},
        "gc_bias_details": {
            "GC": [0, 1],
            "WINDOWS": [10, 10],
            "READ_STARTS": [5, 5],
            "MEAN_BASE_QUALITY": [30.0, 30.0],
            "NORMALIZED_COVERAGE": [1.0, 1.0],
            "ERROR_BAR": [0.1, 0.1],
        },
        "insert_size_metrics": {
            "median_insert_size": 210,
            "mode_insert_size": 200,
            "mean_insert_size": 220.0,
            "standard_deviation": 10.0,
            "read_pairs": 100,
            "width_of_10_percent": 10,
            "width_of_20_percent": 20,
            "width_of_30_percent": 30,
            "width_of_40_percent": 40,
            "width_of_50_percent": 50,
            "width_of_60_percent": 60,
            "width_of_70_percent": 70,
            "width_of_80_percent": 80,
            "width_of_90_percent": 90,
            "width_of_95_percent": 95,
            "width_of_99_percent": 99,
        },
        "insert_size_histogram": {
            "insert_size": [100, 101],
            "pair_orientation": ["FR", "FR"],
            "All_Reads.fr_count": [10, 20],
            "VALUE": [1.0, 2.0],
            "all_sets": [1, 1],
            "optical_sets": [0, 0],
            "non_optical_sets": [1, 1],
        },
        "error_summaries": {
            "REF": ["A", "C"],
            "ALT": ["T", "G"],
            "COUNT": [10, 20],
            "RATE": [0.1, 0.2],
            "QSCORE": [20, 30],
        },
        "pre_adapter_summaries": {
            "ARTIFACT_NAME": ["Deamination"],
            "TOTAL_QSCORE": [5],
            "WORST_CXT": ["ACA"],
            "WORST_CXT_QSCORE": [5],
        },
        "bait_bias_summaries": {
            "ARTIFACT_NAME": ["Cref"],
            "TOTAL_QSCORE": [40],
            "WORST_CXT": ["CCA"],
            "WORST_CXT_QSCORE": [35],
        },
        "conversion_log": {
            "program": "Parabricks",
            "version": "1",
            "start_time": "a",
            "end_time": "b",
            "total_time": "c",
        },
        "duplication_metrics": [
            {
                "LIBRARY": "lib1",
                "UNPAIRED_READS_EXAMINED": 0,
                "READ_PAIRS_EXAMINED": 100,
                "SECONDARY_OR_SUPPLEMENTARY_RDS": 0,
                "UNMAPPED_READS": 0,
                "UNPAIRED_READ_DUPLICATES": 0,
                "READ_PAIR_DUPLICATES": 8,
                "READ_PAIR_OPTICAL_DUPLICATES": 1,
                "PERCENT_DUPLICATION": 0.08,
                "ESTIMATED_LIBRARY_SIZE": 1000,
            }
        ],
        "duplication_histogram": {
            "BIN": [1.0, 2.0],
            "VALUE": [100.0, 20.0],
            "all_sets": [],
            "optical_sets": [],
            "non_optical_sets": [],
        },
        "summary_stats": {
            "total_reads": 1000,
            "duplication_rate": 0.08,
            "estimated_library_size": 1000,
            "duplicate_reads": 80,
            "optical_duplicates": 10,
        },
        "guardrails": {
            "sample_id": "s1",
            "overall_pass": True,
            "details": {
                "pf_percent": {"value": 97.0, "normal_range": ">= 90", "pass": True, "message": "ok"},
                "q30_percent": {"value": 88.0, "normal_range": ">= 85", "pass": True, "message": "ok"},
                "mean_quality": {"value": 35.0, "normal_range": ">= 30", "pass": True, "message": "ok"},
                "min_quality_post20": {"value": 32.0, "normal_range": ">= 28", "pass": True, "message": "ok"},
                "at_dropout": {"value": 1.0, "normal_range": "<= 5", "pass": True, "message": "ok"},
                "gc_dropout": {"value": 2.0, "normal_range": "<= 10", "pass": True, "message": "ok"},
                "median_insert_bp": {"value": 210.0, "normal_range": ">= 150", "pass": True, "message": "ok"},
                "deamination_qscore": {"value": 20.0, "normal_range": ">= 10", "pass": True, "message": "ok"},
                "oxog_qscore": {"value": 25.0, "normal_range": ">= 10", "pass": True, "message": "ok"},
            },
            "recommendation": "r",
            "next_steps": "n",
        },
    }


def test_v1_to_v2_transposes_row_sections():
    v1 = _minimal_v1_dict()
    v2 = v1_dict_to_v2_dict(v1)
    assert v2["metadata"]["schema_version"] == "2.0.0"
    assert len(v2["mean_quality_by_cycle"]["rows"]) == 2
    assert v2["mean_quality_by_cycle"]["rows"][1] == {"cycle": 2, "mean_quality": 37.0}
    assert v2["quality_score_distribution"]["rows"] == [
        {"q": 20, "count_of_q": 100},
        {"q": 30, "count_of_q": 90},
    ]
    assert v2["base_distribution_by_cycle"]["rows"][0]["pct_a"] == 25.0
    assert len(v2["gc_bias_details"]["rows"]) == 2
    assert v2["insert_size_histogram"]["rows"][0]["all_reads_fr_count"] == 10
    assert v2["error_summaries"]["rows"][1]["ref"] == "C"
    assert v2["pre_adapter_summaries"]["rows"][0]["artifact_name"] == "Deamination"
    assert v2["duplication_histogram"]["rows"][0]["bin"] == 1.0
    ExportedSampleQCV2Payload.model_validate(v2)


def test_v2_payload_detected_idempotent_skip(tmp_path: Path):
    v2 = v1_dict_to_v2_dict(_minimal_v1_dict())
    path = tmp_path / "out.json"
    path.write_text(json.dumps(v2), encoding="utf-8")
    ok, msg = convert_file(path, apply=False)
    assert not ok
    assert "SKIP" in msg and "V2" in msg


def test_convert_file_apply_writes_default_v2_suffix(tmp_path: Path):
    v1_path = tmp_path / "sample.json"
    v1_path.write_text(json.dumps(_minimal_v1_dict()), encoding="utf-8")
    ok, msg = convert_file(v1_path, apply=True, validate_v2=True)
    assert ok
    assert "CONVERTED" in msg
    out = tmp_path / "sample.v2.json"
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert is_v2_alignment_qc_payload(loaded)


def test_convert_file_apply_with_backup(tmp_path: Path):
    v1_path = tmp_path / "sample.json"
    v1_path.write_text(json.dumps(_minimal_v1_dict()), encoding="utf-8")
    out = tmp_path / "custom.v2.json"
    out.write_text('{"old": true}', encoding="utf-8")
    ok, msg = convert_file(v1_path, apply=True, backup=True, output_path=out, validate_v2=True)
    assert ok
    assert (tmp_path / "custom.v2.json.bak").exists()


def test_legacy_guardrail_threshold_migrated_then_converted():
    v1 = _minimal_v1_dict()
    v1["guardrails"]["details"]["pf_percent"] = {
        "value": 91.5,
        "threshold": ">= 90",
        "pass": True,
        "note": "PF note",
    }
    v2 = v1_dict_to_v2_dict(v1)
    pf = v2["guardrails"]["details"]["pf_percent"]
    assert pf["normal_range"] == ">= 90"
    assert pf["message"] == "PF note"
    assert "threshold" not in pf
    ExportedSampleQCV2Payload.model_validate(v2)


def test_cli_single_file_dry_run(tmp_path: Path):
    v1_path = tmp_path / "x.json"
    v1_path.write_text(json.dumps(_minimal_v1_dict()), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "methyl_alignment_qc.utils.v1_to_v2_migration", str(v1_path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "WOULD CONVERT" in proc.stdout


def test_end_to_end_writer_output_converts(tmp_path: Path):
    from methyl_alignment_qc.core.writer import process_samples_to_qc_jsons

    sample_dir = tmp_path / "sampleA"
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "sampleA.deduplicate_metrics.txt").write_text(_dedup_metrics_fixture(), encoding="utf-8")
    (sample_dir / "sampleA.json").write_text(
        json.dumps(_parabricks_json_fixture("sampleA")),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    process_samples_to_qc_jsons([str(sample_dir)], str(out_dir), validate_schema=True)
    v1_path = out_dir / "sampleA.json"
    v2_dict = v1_dict_to_v2_dict(json.loads(v1_path.read_text(encoding="utf-8")))
    ExportedSampleQCV2Payload.model_validate(v2_dict)
    assert len(v2_dict["mean_quality_by_cycle"]["rows"]) == 5
