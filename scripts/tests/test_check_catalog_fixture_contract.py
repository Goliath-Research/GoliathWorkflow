"""Tests for scripts/check_catalog_fixture_contract.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_catalog_fixture_contract.py"


def test_catalog_fixture_contract_passes_on_repo() -> None:
    proc = subprocess.run(
        ["python", str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_detects_missing_golden(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("check_catalog", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    root = tmp_path / "repo"
    (root / "schemas" / "actions").mkdir(parents=True)
    (root / "schemas" / "tasks").mkdir(parents=True)
    (root / "workers" / "tests" / "golden").mkdir(parents=True)

    (root / "schemas" / "tasks" / "sample_demo.input.schema.json").write_text("{}", encoding="utf-8")
    (root / "schemas" / "tasks" / "sample_demo.output.schema.json").write_text("{}", encoding="utf-8")
    (root / "schemas" / "actions" / "catalog.json").write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "action_name": "sample.demo",
                        "input_schema_ref": "schemas/tasks/sample_demo.input.schema.json",
                        "output_schema_ref": "schemas/tasks/sample_demo.output.schema.json",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "workers" / "tests" / "golden_fixtures_data.py").write_text(
        textwrap.dedent(
            '''
            GOLDEN_INPUTS = {}
            GOLDEN_OUTPUTS = {}
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    errors = mod.check_catalog_fixture_contract(root)
    assert any("missing golden input" in e for e in errors)
    assert any("golden_fixtures_data.py" in e for e in errors)
