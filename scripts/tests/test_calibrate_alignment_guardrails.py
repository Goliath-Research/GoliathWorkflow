"""Smoke tests for calibrate_alignment_guardrails.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_calibrate_script_on_synthetic_qc_dir(tmp_path: Path) -> None:
    qc_dir = tmp_path / "qc"
    qc_dir.mkdir()
    payload = {
        "sample_id": "S1",
        "duplication_metrics": [
            {
                "LIBRARY": "lib1",
                "UNPAIRED_READS_EXAMINED": 0,
                "READ_PAIRS_EXAMINED": 1000,
                "SECONDARY_OR_SUPPLEMENTARY_RDS": 5,
                "UNMAPPED_READS": 2,
                "UNPAIRED_READ_DUPLICATES": 0,
                "READ_PAIR_DUPLICATES": 0,
                "READ_PAIR_OPTICAL_DUPLICATES": 0,
                "PERCENT_DUPLICATION": 0.0,
                "ESTIMATED_LIBRARY_SIZE": 1000,
            }
        ],
        "gc_bias_details": {
            "WINDOWS": [10, 10],
            "NORMALIZED_COVERAGE": [0.9, 1.0],
        },
        "alignment_flagstat": {
            "properly_paired_rate": 0.95,
            "supplementary_rate": 0.01,
        },
    }
    (qc_dir / "S1.json").write_text(json.dumps(payload), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/calibrate_alignment_guardrails.py"), "--qc-dir", str(qc_dir)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert "mapping_rate" in proc.stdout
