"""Cohort screening reads stored guardrails.screening on slim V2.1 exports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alignment_qc_cohort_screening import screen_one_qc_json
from methyl_alignment_qc.models.config import CycleScreeningConfig, OptionalGuardrailsConfig


def test_screen_one_qc_json_uses_stored_screening_by_default(tmp_path: Path) -> None:
    qc_path = tmp_path / "s1.json"
    qc_path.write_text(
        json.dumps(
            {
                "sample_id": "s1",
                "guardrails": {
                    "overall_pass": True,
                    "details": {
                        "q30_percent": {
                            "value": 90.0,
                            "normal_range": ">= 85",
                            "pass": True,
                            "message": "ok",
                        }
                    },
                    "screening": {
                        "disposition": "USE_CURRENT_ALIGNMENT",
                        "trim_front2": 0,
                        "message": "stored",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    row = screen_one_qc_json(
        qc_path,
        cycle_cfg=CycleScreeningConfig(),
        opt_cfg=OptionalGuardrailsConfig(),
        recompute=False,
    )
    assert row["screening"]["disposition"] == "USE_CURRENT_ALIGNMENT"
    assert row["screening"]["message"] == "stored"
    assert row["failed_guardrails"] == []
