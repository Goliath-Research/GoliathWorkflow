"""Implementation of ``methyl-cfg verify-workflow``."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _domain_dir(repo_root: Path) -> Path:
    return repo_root / "workflow_engine" / "domain"


def run_verify_workflow(
    *,
    program: Path,
    repo_root: Path,
    site_path: Optional[Path] = None,
    procedure_path: Optional[Path] = None,
    check_db: bool = False,
    workflow_name: Optional[str] = None,
) -> Dict[str, Any]:
    domain = _domain_dir(repo_root)
    if str(domain) not in sys.path:
        sys.path.insert(0, str(domain))
    from verify_workflow import (  # type: ignore
        compare_compiled_to_db_nodes,
        verify_methylgrapher_bake,
        verify_program_file,
    )
    from compiler import compile_domain_program_file  # type: ignore

    report = verify_program_file(program)
    payload: Dict[str, Any] = report.to_dict()

    bake_findings: List[Dict[str, str]] = []
    if site_path and site_path.is_file():
        site = json.loads(site_path.read_text(encoding="utf-8"))
        profile_ac = None
        if procedure_path and procedure_path.is_file():
            proc = json.loads(procedure_path.read_text(encoding="utf-8"))
            profile_ac = proc.get("actionConfig")
        for f in verify_methylgrapher_bake(site, profile_ac):
            bake_findings.append(
                {"severity": f.severity, "code": f.code, "message": f.message}
            )
            report.findings.append(f)
    payload["methylgrapher_bake"] = bake_findings

    db_findings: List[Dict[str, str]] = []
    if check_db:
        compiled = compile_domain_program_file(program, enrich_context=False)
        name = workflow_name or compiled.workflow.name
        db_nodes = _fetch_db_action_nodes(name)
        for f in compare_compiled_to_db_nodes(compiled, db_nodes):
            db_findings.append(
                {"severity": f.severity, "code": f.code, "message": f.message}
            )
            report.findings.append(f)
    payload["db_compare"] = db_findings
    payload["ok"] = report.ok
    payload["findings"] = [
        {"severity": f.severity, "code": f.code, "message": f.message}
        for f in report.findings
    ]
    return payload


def _fetch_db_action_nodes(workflow_name: str) -> List[Dict[str, Any]]:
    """Load ACTION nodes for the active version of ``workflow_name`` from Azure SQL."""
    import pyodbc

    server = os.environ.get("AZURE_SQL_SERVER")
    db = os.environ.get("AZURE_SQL_DB")
    user = os.environ.get("AZURE_SQL_USER")
    password = os.environ.get("AZURE_SQL_PASSWORD")
    if not all([server, db, user, password]):
        raise RuntimeError(
            "check-db requires AZURE_SQL_SERVER/DB/USER/PASSWORD (e.g. gateway.env)"
        )
    cs = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};"
        f"DATABASE={db};UID={user};PWD={password};Encrypt=yes;TrustServerCertificate=no"
    )
    conn = pyodbc.connect(cs, timeout=30)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT TOP 1 wv.id
        FROM wf.workflow_version wv
        JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id
        WHERE wd.name = ? AND wv.is_active = 1
        ORDER BY wv.id DESC
        """,
        workflow_name,
    )
    row = cur.fetchone()
    if not row:
        return []
    version_id = int(row[0])
    cur.execute(
        """
        SELECT wn.node_key, wn.node_type, wa.action_name
        FROM wf.workflow_node wn
        LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
        WHERE wn.workflow_version_id = ?
        """,
        version_id,
    )
    return [
        {
            "node_key": r.node_key,
            "node_type": r.node_type,
            "action_name": r.action_name,
        }
        for r in cur.fetchall()
    ]
