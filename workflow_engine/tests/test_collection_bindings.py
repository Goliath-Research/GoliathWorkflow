"""Integration tests for engine-side collection binding resolution."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SQL_PG = ROOT / "sql_pg"


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


def _schema_ready(dsn: str) -> bool:
    try:
        out = _psql_query(
            dsn,
            "SELECT to_regnamespace('wf') IS NOT NULL AND to_regclass('wf.workflow_def') IS NOT NULL;",
        )
        return out == "t"
    except subprocess.CalledProcessError:
        return False


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    return _pg_dsn()


@pytest.mark.integration
def test_resolve_collection_bindings_from_inline_project(pg_dsn: str) -> None:
    if not _schema_ready(pg_dsn):
        pytest.skip("PostgreSQL wf schema not available")

    for name in (
        "wf_sql_collection_bindings.sql",
        "wf_repo_create_workflow_graph.sql",
        "01_worker_api.sql",
    ):
        _run_psql(pg_dsn, SQL_PG / name)

    project_doc = {
        "chromosomes": ["1", "2"],
        "contexts": ["CG"],
        "comparisons": [{"label": "a_vs_b", "control_group": "a", "disease_group": "b"}],
    }
    spec = {
        "name": "CollectionBindingTest",
        "root_node_key": "root",
        "nodes": [{"node_key": "root", "node_type": "SEQUENCE"}],
        "collection_bindings": [
            {
                "scope_var": "project",
                "kind": "jsonFile",
                "path_var": "projectPath",
                "bind_order": 0,
            },
            {
                "scope_var": "chromosomes",
                "kind": "jsonPath",
                "base_var": "project",
                "json_path": "$.chromosomes",
                "bind_order": 1,
            },
        ],
    }
    spec_json = json.dumps(spec).replace("'", "''")
    ctx_json = json.dumps({"projectPath": "/nonexistent", "project": project_doc}).replace("'", "''")

    created = _psql_query(
        pg_dsn,
        f"SELECT wf.wf_repo_create_workflow_graph('{spec_json}'::jsonb)::text;",
    )
    version_id = json.loads(created)["workflow_version_id"]

    instance_id = _psql_query(
        pg_dsn,
        f"SELECT wf.wf_repo_create_workflow_instance({version_id}, '{ctx_json}'::jsonb);",
    )

    _psql_query(pg_dsn, f"CALL wf.wf_init_instance_scope_from_context({instance_id});")
    _psql_query(pg_dsn, f"CALL wf.wf_resolve_collection_bindings({instance_id});")

    chrom = _psql_query(
        pg_dsn,
        f"""
        SELECT value_json::text
        FROM wf.scope_variable
        WHERE workflow_instance_id = {instance_id}
          AND scope_node_execution_id = 0
          AND var_name = 'chromosomes';
        """,
    )
    assert json.loads(chrom) == ["1", "2"]

    _psql_query(
        pg_dsn,
        "SELECT wf.sp_delete_workflow_def(NULL, 'CollectionBindingTest', true);",
    )
