#!/usr/bin/env python3
"""Parity test: programmatic workflow definition builder (wf_repo_create_workflow_graph)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SQL_PG = ROOT / "sql_pg"
sys.path.insert(0, str(ROOT / "contract"))
sys.path.insert(0, str(ROOT.parent / "workers"))

from workflow_definition_spec import WorkflowDefinitionSpec  # noqa: E402


def _pg_dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "methylpipeline_parity")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "methyl")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _pg_env() -> dict[str, str]:
    env = os.environ.copy()
    if "PGPASSWORD" not in env and os.environ.get("POSTGRES_PASSWORD"):
        env["PGPASSWORD"] = os.environ["POSTGRES_PASSWORD"]
    return env


def _run_psql(dsn: str, sql_path: Path) -> None:
    subprocess.run(
        ["psql", "-q", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(sql_path)],
        check=True,
        capture_output=True,
        text=True,
        env=_pg_env(),
    )


def _psql_query(dsn: str, sql: str) -> str:
    proc = subprocess.run(
        ["psql", "-q", dsn, "-t", "-A", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
        env=_pg_env(),
    )
    return proc.stdout.strip()


def deploy_builder_procs(dsn: str) -> None:
    try:
        _psql_query(dsn, "SELECT 1 FROM wf.workflow_def LIMIT 1;")
    except subprocess.CalledProcessError:
        pytest.skip("wf schema not deployed; run workflow_engine/sql_pg deploy scripts first")

    for name in (
        "wf_sql_collection_bindings.sql",
        "wf_repo_upsert_workflow_action.sql",
        "wf_repo_create_workflow_graph.sql",
    ):
        _run_psql(dsn, SQL_PG / name)


def _postgres_available() -> bool:
    try:
        subprocess.run(
            ["psql", _pg_dsn(), "-c", "SELECT 1"],
            check=True,
            capture_output=True,
            text=True,
            env=_pg_env(),
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


@pytest.mark.skipif(not _postgres_available(), reason="PostgreSQL parity database not available")
def test_create_workflow_graph_and_start() -> None:
    dsn = _pg_dsn()
    deploy_builder_procs(dsn)

    _psql_query(
        dsn,
        "CALL wf.wf_repo_upsert_workflow_action('pipeline.centroid', 'methyl-centroid', 'pipeline.centroid');",
    )

    spec = WorkflowDefinitionSpec(
        name="BuilderParityFlow",
        description="Minimal graph created via wf_repo_create_workflow_graph",
        root_node_key="root",
        nodes=[
            {"node_key": "root", "node_type": "SEQUENCE"},
            {
                "node_key": "centroid",
                "node_type": "ACTION",
                "action_name": "pipeline.centroid",
                "input_template": {
                    "tool": "MethylCentroid",
                    "project": "${var.projectPath}",
                },
            },
        ],
        edges=[
            {
                "parent_node_key": "root",
                "child_node_key": "centroid",
                "child_order": 0,
                "branch_kind": "SEQUENCE",
            }
        ],
    )
    spec_json = json.dumps(spec.to_db_spec()).replace("'", "''")
    result_raw = _psql_query(
        dsn,
        f"SELECT wf.wf_repo_create_workflow_graph('{spec_json}'::jsonb)::text;",
    )
    result = json.loads(result_raw)
    version_id = int(result["workflow_version_id"])
    root_node_id = int(result["root_node_id"])

    stored_root = _psql_query(
        dsn,
        f"SELECT root_node_id FROM wf.workflow_version WHERE id = {version_id};",
    )
    assert int(stored_root) == root_node_id

    node_count = _psql_query(
        dsn,
        f"SELECT count(*) FROM wf.workflow_node WHERE workflow_version_id = {version_id};",
    )
    assert int(node_count) == 2

    instance_id = int(
        _psql_query(
            dsn,
            f"SELECT id FROM wf.wf_repo_create_workflow_instance({version_id}, '{{}}'::jsonb);",
        )
    )
    _psql_query(dsn, f"CALL wf.sp_start_workflow_instance({instance_id});")
    exec_count = int(
        _psql_query(
            dsn,
            f"SELECT count(*) FROM wf.node_execution WHERE workflow_instance_id = {instance_id};",
        )
    )
    assert exec_count >= 1
    status = _psql_query(
        dsn,
        f"SELECT status FROM wf.workflow_instance WHERE id = {instance_id};",
    )
    assert status != "CREATED"


if __name__ == "__main__":
    test_create_workflow_graph_and_start()
    print("workflow builder parity test passed")
