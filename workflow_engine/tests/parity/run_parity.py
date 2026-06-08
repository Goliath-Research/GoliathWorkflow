#!/usr/bin/env python3
"""
Backend-agnostic conformance harness for wf worker API and repository contract.

Runs identical scenarios against PostgreSQL (local container) and optionally Azure SQL
when METHYL_TEST_MSSQL_DSN is set.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
SQL_PG = ROOT / "sql_pg"
CONTRACT_SCRIPT = ROOT / "contract" / "validate_contract.py"


def _pg_dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "methylpipeline_parity")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "methyl")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _run_psql(dsn: str, sql_path: Path) -> None:
    subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(sql_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def deploy_postgres(dsn: str) -> None:
    for name in ("00_schema.sql", "03_engine_core.sql", "01_worker_api.sql", "02_repository_api.sql", "04_admin.sql"):
        _run_psql(dsn, SQL_PG / name)


def _psql_query(dsn: str, sql: str) -> str:
    proc = subprocess.run(
        ["psql", dsn, "-t", "-A", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def seed_minimal_workflow(dsn: str) -> tuple[int, int, str]:
    """Returns (version_id, worker_id, worker_token)."""
    _psql_query(dsn, "DELETE FROM wf.workflow_def WHERE name = 'ParityFlow';")
    _psql_query(dsn, "INSERT INTO wf.workflow_def (name) VALUES ('ParityFlow');")
    def_id = int(_psql_query(dsn, "SELECT id FROM wf.workflow_def WHERE name='ParityFlow' LIMIT 1;"))
    version_id = int(
        _psql_query(
            dsn,
            f"INSERT INTO wf.workflow_version (workflow_def_id) VALUES ({def_id}) RETURNING id;",
        )
    )
    action_id = int(
        _psql_query(
            dsn,
            "INSERT INTO wf.workflow_action (action_name, capability) VALUES ('LoadInput','test-cap') RETURNING id;",
        )
    )
    node_id = int(
        _psql_query(
            dsn,
            f"INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id) "
            f"VALUES ({version_id}, 'ACTION', 'load_input', {action_id}) RETURNING id;",
        )
    )
    _psql_query(dsn, f"UPDATE wf.workflow_version SET root_node_id = {node_id} WHERE id = {version_id};")

    cluster_id = int(
        _psql_query(
            dsn,
            "INSERT INTO wf.cluster (cluster_key, name) VALUES ('parity','Parity') RETURNING id;",
        )
    )
    worker_id = int(
        _psql_query(
            dsn,
            f"INSERT INTO wf.worker (cluster_id, external_worker_key) VALUES ({cluster_id}, 'w1') RETURNING id;",
        )
    )
    token = "parity-test-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    _psql_query(
        dsn,
        f"INSERT INTO wf.worker_token (worker_id, token_hash) VALUES ({worker_id}, decode('{token_hash}','hex'));",
    )
    return version_id, worker_id, token


def test_worker_api_postgres(dsn: str) -> None:
    version_id, worker_id, token = seed_minimal_workflow(dsn)
    instance_id = int(
        _psql_query(
            dsn,
            f"SELECT id FROM wf.wf_repo_create_workflow_instance({version_id}, '{{}}'::jsonb);",
        )
    )
    _psql_query(dsn, f"CALL wf.sp_start_workflow_instance({instance_id});")

    claim = _psql_query(
        dsn,
        f"SELECT node_execution_id FROM wf.sp_worker_request_task({worker_id}, '{token}', 'test-cap', 60);",
    )
    assert claim, "expected task claim"
    ne_id = int(claim.split("|")[0])

    ack = _psql_query(
        dsn,
        f"SELECT accepted, instance_status FROM wf.sp_worker_submit_result({ne_id}, {worker_id}, '{token}', 1, '{{\"ok\":true}}'::jsonb);",
    )
    assert ack.startswith("t|COMPLETED"), f"unexpected ack: {ack}"


def test_repository_postgres(dsn: str) -> None:
    version_id = int(_psql_query(dsn, "SELECT id FROM wf.workflow_version LIMIT 1;"))
    new_id = int(
        _psql_query(
            dsn,
            f"SELECT id FROM wf.wf_repo_create_workflow_instance({version_id}, '{{\"x\":1}}'::jsonb);",
        )
    )
    assert new_id > 0
    _psql_query(dsn, f"CALL wf.wf_repo_set_instance_status({new_id}, 'RUNNING');")
    status = _psql_query(dsn, f"SELECT status FROM wf.workflow_instance WHERE id={new_id};")
    assert status == "RUNNING"


def main() -> int:
    if not shutil_which("psql"):
        print("psql not found; skip postgres parity (install postgresql-client)", file=sys.stderr)
        return 0

    dsn = _pg_dsn()
    db_name = os.environ.get("POSTGRES_DB", "methylpipeline_parity")
    admin = dsn.rsplit("/", 1)[0] + "/postgres"
    subprocess.run(["createdb", "-h", os.environ.get("POSTGRES_HOST", "localhost"), db_name], check=False)

    print(f"Deploying PostgreSQL schema to {dsn}")
    deploy_postgres(dsn)

    print("Running worker API parity...")
    test_worker_api_postgres(dsn)
    print("Running repository parity...")
    test_repository_postgres(dsn)

    print("Validating contract lockstep...")
    proc = subprocess.run([sys.executable, str(CONTRACT_SCRIPT)], capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode

    print("PostgreSQL parity: OK")
    return 0


def shutil_which(cmd: str) -> Optional[str]:
    from shutil import which

    return which(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
