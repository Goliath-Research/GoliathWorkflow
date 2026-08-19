"""Twin check for sql_mssql/deploy_azure.sh and sql_pg/deploy_azure.sh."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "scripts" / "check_sql_deploy_twins.py"


def test_sql_deploy_twins_pass() -> None:
    proc = subprocess.run(
        ["python3", str(CHECK)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "twins OK" in proc.stdout


def test_deploy_azure_scripts_declare_twin() -> None:
    mssql = (REPO_ROOT / "workflow_engine/sql_mssql/deploy_azure.sh").read_text(
        encoding="utf-8"
    )
    pg = (REPO_ROOT / "workflow_engine/sql_pg/deploy_azure.sh").read_text(encoding="utf-8")
    assert "sql_pg/deploy_azure.sh" in mssql
    assert "sql_mssql/deploy_azure.sh" in pg
    assert "check_sql_deploy_twins.py" in mssql
    assert "check_sql_deploy_twins.py" in pg
