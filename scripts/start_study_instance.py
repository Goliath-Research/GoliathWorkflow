#!/usr/bin/env python3
"""Compatibility wrapper → ``methyl-study-start`` Admin CLI.

Prefer ``methyl-study-start`` directly. This script remains for older smoke docs.
"""

from __future__ import annotations

import sys
from pathlib import Path

WF_ENGINE = Path(__file__).resolve().parents[1] / "workflow_engine"
sys.path.insert(0, str(WF_ENGINE))

from admin.study_start import main  # noqa: E402


if __name__ == "__main__":
    # Map legacy: start_study_instance.py <cmd> [file] → methyl-study-start <cmd> [file]
    raise SystemExit(main())
