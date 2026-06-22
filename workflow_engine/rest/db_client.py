"""Workflow REST gateway database facade (backend-agnostic)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator, Optional, Union

from .connection import resolve_connection_config
from .db import open_gateway_db
from .db.base import GatewayDb, WorkerAuthError

# Backward-compatible alias for parity scripts that build a PostgreSQL URL.
def pg_dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "methylpipeline_parity")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "methyl")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def open_db_from_dsn(dsn: str) -> GatewayDb:
    """Open a PostgreSQL GatewayDb from a libpq-style connection URL."""
    from .db.postgres import PostgresGatewayDb

    return PostgresGatewayDb(dsn, schema_name=resolve_connection_config().schema_name)


@contextmanager
def _use_db(db_or_dsn: Union[GatewayDb, str]) -> Generator[GatewayDb, None, None]:
    """Yield a GatewayDb; close ephemeral pools opened from a DSN string."""
    if isinstance(db_or_dsn, str):
        db = open_db_from_dsn(db_or_dsn)
        try:
            yield db
        finally:
            db.close()
    else:
        yield db_or_dsn


def worker_authenticate(db_or_dsn: Union[GatewayDb, str], worker_id: int, worker_token: str) -> None:
    with _use_db(db_or_dsn) as db:
        db.worker_authenticate(worker_id, worker_token)


def worker_request_task(
    db_or_dsn: Union[GatewayDb, str],
    worker_id: int,
    worker_token: str,
    capability: Optional[str],
    max_lease_seconds: int,
) -> dict[str, Any]:
    with _use_db(db_or_dsn) as db:
        return db.worker_request_task(
            worker_id, worker_token, capability, max_lease_seconds
        )


def worker_submit_result(
    db_or_dsn: Union[GatewayDb, str],
    node_execution_id: int,
    worker_id: int,
    worker_token: str,
    result_code: int,
    output_json: Optional[dict[str, Any]],
) -> dict[str, Any]:
    with _use_db(db_or_dsn) as db:
        return db.worker_submit_result(
            node_execution_id, worker_id, worker_token, result_code, output_json
        )


def worker_heartbeat(
    db_or_dsn: Union[GatewayDb, str],
    node_execution_id: int,
    worker_id: int,
    worker_token: str,
    extend_seconds: int,
) -> dict[str, int]:
    with _use_db(db_or_dsn) as db:
        return db.worker_heartbeat(
            node_execution_id, worker_id, worker_token, extend_seconds
        )


def worker_fail_task(
    db_or_dsn: Union[GatewayDb, str],
    node_execution_id: int,
    worker_id: int,
    worker_token: str,
    error_code: int,
    error_message: Optional[str],
) -> None:
    with _use_db(db_or_dsn) as db:
        db.worker_fail_task(
            node_execution_id, worker_id, worker_token, error_code, error_message
        )


def create_workflow_instance(
    db_or_dsn: Union[GatewayDb, str],
    workflow_version_id: int,
    context_json: Optional[dict[str, Any]],
) -> int:
    with _use_db(db_or_dsn) as db:
        return db.create_workflow_instance(workflow_version_id, context_json)


def start_workflow_instance(db_or_dsn: Union[GatewayDb, str], instance_id: int) -> None:
    with _use_db(db_or_dsn) as db:
        db.start_workflow_instance(instance_id)


def get_workflow_instance(db_or_dsn: Union[GatewayDb, str], instance_id: int) -> dict[str, Any]:
    with _use_db(db_or_dsn) as db:
        return db.get_workflow_instance(instance_id)


def delete_workflow_definition(
    db_or_dsn: Union[GatewayDb, str],
    name: str,
    delete_instances: bool,
) -> dict[str, int]:
    with _use_db(db_or_dsn) as db:
        return db.delete_workflow_definition(name, delete_instances)


def apply_validation_plan(
    db_or_dsn: Union[GatewayDb, str],
    workflow_instance_id: int,
    context_json: dict[str, Any],
    *,
    persist_extension: bool = True,
) -> None:
    with _use_db(db_or_dsn) as db:
        db.apply_validation_plan(
            workflow_instance_id, context_json, persist_extension=persist_extension
        )


def list_workflow_actions(db_or_dsn: Union[GatewayDb, str]) -> list[dict[str, Any]]:
    with _use_db(db_or_dsn) as db:
        return db.list_workflow_actions()


def get_action_schema(db_or_dsn: Union[GatewayDb, str], action_name: str, direction: str) -> dict[str, Any]:
    with _use_db(db_or_dsn) as db:
        return db.get_action_schema(action_name, direction)


def upsert_workflow_action(
    db_or_dsn: Union[GatewayDb, str],
    action_name: str,
    capability: Optional[str],
    payload_schema_ref: Optional[str] = None,
) -> None:
    with _use_db(db_or_dsn) as db:
        db.upsert_workflow_action(action_name, capability, payload_schema_ref)


def create_workflow_definition(db_or_dsn: Union[GatewayDb, str], spec: dict[str, Any]) -> dict[str, Any]:
    with _use_db(db_or_dsn) as db:
        return db.create_workflow_definition(spec)


__all__ = [
    "GatewayDb",
    "WorkerAuthError",
    "apply_validation_plan",
    "create_workflow_definition",
    "create_workflow_instance",
    "delete_workflow_definition",
    "get_action_schema",
    "get_workflow_instance",
    "list_workflow_actions",
    "open_db_from_dsn",
    "open_gateway_db",
    "pg_dsn",
    "resolve_connection_config",
    "start_workflow_instance",
    "upsert_workflow_action",
    "worker_authenticate",
    "worker_fail_task",
    "worker_heartbeat",
    "worker_request_task",
    "worker_submit_result",
]
