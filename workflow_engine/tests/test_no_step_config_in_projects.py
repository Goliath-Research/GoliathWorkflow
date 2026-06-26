"""CI guard: committed project*.json must not contain step_config."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_no_step_config.py"


def test_no_step_config_in_committed_project_json() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_check_script_detects_step_config(tmp_path: Path) -> None:
    bad = tmp_path / "project_bad.json"
    bad.write_text(json.dumps({"project_name": "x", "step_config": {}}), encoding="utf-8")

    import importlib.util

    spec = importlib.util.spec_from_file_location("check_no_step_config", CHECK_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    violations = mod.find_project_files_with_step_config(tmp_path)
    assert violations == [("project_bad.json", "contains forbidden top-level key 'step_config'")]
