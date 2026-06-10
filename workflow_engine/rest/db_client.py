"""PostgreSQL-backed DB client for the workflow REST gateway (parity / CI)."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Optional


def pg_dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "methylpipeline_parity")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "methyl")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (dict, list)):
        escaped = json.dumps(value).replace("'", "''")
        return f"'{escaped}'::jsonb"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def query_json(dsn: str, sql: str) -> Any:
    wrapped = f"SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM ({sql}) t;"
    proc = subprocess.run(
        ["psql", dsn, "-t", "-A", "-c", wrapped],
        check=True,
        capture_output=True,
        text=True,
    )
    raw = proc.stdout.strip()
    if not raw:
        return []
    return json.loads(raw)


def query_scalar(dsn: str, sql: str) -> Optional[str]:
    proc = subprocess.run(
        ["psql", dsn, "-t", "-A", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
    )
    out = proc.stdout.strip()
    return out if out else None


def exec_sql(dsn: str, sql: str) -> None:
    subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
    )


def worker_authenticate(dsn: str, worker_id: int, worker_token: str) -> None:
    exec_sql(
        dsn,
        f"CALL wf.wf_worker_authenticate({worker_id}, {_sql_literal(worker_token)});",
    )


def worker_request_task(
    dsn: str,
    worker_id: int,
    worker_token: str,
    capability: Optional[str],
    max_lease_seconds: int,
) -> dict[str, Any]:
    cap = _sql_literal(capability) if capability else "NULL"
    rows = query_json(
        dsn,
        f"SELECT * FROM wf.sp_worker_request_task("
        f"{worker_id}, {_sql_literal(worker_token)}, {cap}, {max_lease_seconds})",
    )
    if not rows:
        return {"has_task": False}
    row = rows[0]
    return {
        "has_task": True,
        "node_execution_id": row["node_execution_id"],
        "workflow_instance_id": row["workflow_instance_id"],
        "node_key": row["node_key"],
        "action_name": row["action_name"],
        "capability": row["capability"],
        "attempt_no": row["attempt_no"],
        "input_json": row.get("input_json") or {},
        "iteration_no": row["iteration_no"],
    }


def worker_submit_result(
    dsn: str,
    node_execution_id: int,
    worker_id: int,
    worker_token: str,
    result_code: int,
    output_json: Optional[dict[str, Any]],
) -> dict[str, Any]:
    out = _sql_literal(output_json) if output_json is not None else "NULL"
    rows = query_json(
        dsn,
        f"SELECT * FROM wf.sp_worker_submit_result("
        f"{node_execution_id}, {worker_id}, {_sql_literal(worker_token)}, "
        f"{result_code}, {out})",
    )
    return rows[0] if rows else {"accepted": False}


def worker_heartbeat(
    dsn: str,
    node_execution_id: int,
    worker_id: int,
    worker_token: str,
    extend_seconds: int,
) -> dict[str, int]:
    rows = query_json(
        dsn,
        f"SELECT * FROM wf.sp_worker_heartbeat("
        f"{node_execution_id}, {worker_id}, {_sql_literal(worker_token)}, {extend_seconds})",
    )
    return {"rows_updated": int(rows[0]["rows_updated"]) if rows else 0}


def worker_fail_task(
    dsn: str,
    node_execution_id: int,
    worker_id: int,
    worker_token: str,
    error_code: int,
    error_message: Optional[str],
) -> None:
    msg = _sql_literal(error_message) if error_message else "NULL"
    exec_sql(
        dsn,
        f"CALL wf.sp_worker_fail_task("
        f"{node_execution_id}, {worker_id}, {_sql_literal(worker_token)}, "
        f"{error_code}, {msg});",
    )


def create_workflow_instance(
    dsn: str, workflow_version_id: int, context_json: Optional[dict[str, Any]]
) -> int:
    ctx = _sql_literal(context_json or {})
    row_id = query_scalar(
        dsn,
        f"SELECT id FROM wf.wf_repo_create_workflow_instance({workflow_version_id}, {ctx});",
    )
    return int(row_id)


def start_workflow_instance(dsn: str, instance_id: int) -> None:
    exec_sql(dsn, f"CALL wf.sp_start_workflow_instance({instance_id});")


def get_workflow_instance(dsn: str, instance_id: int) -> dict[str, Any]:
    rows = query_json(
        dsn,
        f"SELECT id, workflow_version_id, status FROM wf.workflow_instance WHERE id = {instance_id}",
    )
    if not rows:
        raise KeyError(f"instance {instance_id} not found")
    return rows[0]


def delete_workflow_definition(dsn: str, name: str, delete_instances: bool) -> dict[str, int]:
    rows = query_json(
        dsn,
        f"SELECT * FROM wf.sp_delete_workflow_def(NULL, {_sql_literal(name)}, {delete_instances});",
    )
    row = rows[0] if rows else {"deleted_instance_count": 0, "deleted_version_count": 0}
    return {
        "deleted_instance_count": int(row["deleted_instance_count"]),
        "deleted_version_count": int(row["deleted_version_count"]),
    }


def apply_validation_plan(
    dsn: str,
    workflow_instance_id: int,
    context_json: dict[str, Any],
    *,
    persist_extension: bool = True,
) -> None:
    """Merge ValidationPipeline planner output into instance context (wf.wf_apply_validation_plan)."""
    exec_sql(
        dsn,
        "CALL wf.wf_apply_validation_plan("
        f"{workflow_instance_id}, {_sql_literal(context_json)}, {persist_extension});",
    )
