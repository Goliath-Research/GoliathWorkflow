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
