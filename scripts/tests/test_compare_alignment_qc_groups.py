"""Tests for compare_alignment_qc_groups sample_id handling."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_alignment_qc_groups import flatten_qc_json, load_group_rows


def test_flatten_qc_json_does_not_emit_canonical_sample_id(tmp_path: Path) -> None:
    qc_path = tmp_path / "canonical-id.json"
    qc_path.write_text(
        json.dumps(
            {
                "sample_id": "internal-wrong-id",
                "summary_stats": {"total_reads": 100, "duplication_rate": 0.1},
                "quality_yield": {"total_reads": 100, "pf_reads": 90},
                "guardrails": {"overall_pass": True, "details": {}},
            }
        ),
        encoding="utf-8",
    )
    flat = flatten_qc_json(qc_path)
    assert "sample_id" not in flat
    assert flat["qc_json_sample_id"] == "internal-wrong-id"


def test_load_group_rows_keeps_csv_sample_id_when_json_differs(tmp_path: Path) -> None:
    qc_dir = tmp_path / "qc"
    qc_dir.mkdir()
    qc_path = qc_dir / "canonical-id.json"
    qc_path.write_text(
        json.dumps(
            {
                "sample_id": "internal-wrong-id",
                "summary_stats": {"total_reads": 50, "duplication_rate": 0.2},
                "quality_yield": {},
                "guardrails": {"overall_pass": False, "details": {}},
            }
        ),
        encoding="utf-8",
    )
    rows = load_group_rows("g1", ["canonical-id"], qc_dir)
    assert len(rows) == 1
    assert rows[0]["sample_id"] == "canonical-id"
    assert rows[0]["qc_json_sample_id"] == "internal-wrong-id"
    assert rows[0]["qc_status"] == "ok"


def test_flatten_qc_json_reads_guardrails_details_only(tmp_path: Path) -> None:
    qc_path = tmp_path / "s1.json"
    qc_path.write_text(
        json.dumps(
            {
                "sample_id": "s1",
                "summary_stats": {"total_reads": 1000, "duplication_rate": 0.08},
                "quality_yield": {"total_reads": 9999, "pf_reads": 1},
                "alignment_stats": {"mapping_rate": 0.99},
                "guardrails": {
                    "overall_pass": False,
                    "details": {
                        "q30_percent": {
                            "value": 88.0,
                            "normal_range": ">= 85",
                            "pass": True,
                            "message": "ok",
                        },
                        "deamination_qscore": {
                            "value": 15.0,
                            "normal_range": "<= 30",
                            "pass": True,
                            "message": "ok",
                        },
                        "bisulfite_conversion": {
                            "conversion_rate_pct": {
                                "value": 99.5,
                                "normal_range": ">= 99",
                                "pass": True,
                                "message": "ok",
                            },
                        },
                    },
                    "screening": {"disposition": "USE_CURRENT_ALIGNMENT", "trim_front2": 0},
                },
            }
        ),
        encoding="utf-8",
    )
    flat = flatten_qc_json(qc_path)
    assert "quality_yield_total_reads" not in flat
    assert "mapping_rate" not in flat
    assert flat["summary_duplication_rate"] == 0.08
    assert flat["guardrail_q30_percent"] == 88.0
    assert flat["guardrail_deamination_qscore"] == 15.0
    assert flat["guardrail_bisulfite_conversion_conversion_rate_pct"] == 99.5
    assert "guardrail_bisulfite_conversion_deamination_qscore" not in flat
    assert flat["screening_disposition"] == "USE_CURRENT_ALIGNMENT"
