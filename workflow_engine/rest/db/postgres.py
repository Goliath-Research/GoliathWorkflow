"""PostgreSQL gateway database backend (psycopg3)."""

from __future__ import annotations

import json
import queue
import threading
from contextlib import contextmanager
from typing import Any, Generator, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..azure_auth import get_database_access_token
from ..connection import DatabaseBackend
from .base import GatewayDbBase, WorkerAuthError, parse_json_value


class _PgPool:
    """Thread-safe pool; refreshes Entra token on each new connection when MI is enabled."""

    def __init__(
        self,
        conninfo: str,
        *,
        use_managed_identity: bool = False,
        max_size: int = 8,
    ) -> None:
        self._conninfo = conninfo
        self._use_managed_identity = use_managed_identity
        self._max_size = max_size
        self._pool: queue.Queue[psycopg.Connection] = queue.Queue(maxsize=max_size)
        self._lock = threading.Lock()
        self._created = 0

    def _new_connection(self) -> psycopg.Connection:
        if self._use_managed_identity:
            token = get_database_access_token(DatabaseBackend.POSTGRES)
            return psycopg.connect(self._conninfo, password=token, row_factory=dict_row)
        return psycopg.connect(self._conninfo, row_factory=dict_row)

    @contextmanager
    def connection(self) -> Generator[psycopg.Connection, None, None]:
        conn: Optional[psycopg.Connection] = None
        try:
            conn = self._pool.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._created < self._max_size:
                    conn = self._new_connection()
                    self._created += 1
                else:
                    conn = None
            if conn is None:
                conn = self._pool.get()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            try:
                self._pool.put_nowait(conn)
            except queue.Full:
                conn.close()
                with self._lock:
                    self._created -= 1

    def close(self) -> None:
        while True:
            try:
                conn = self._pool.get_nowait()
            except queue.Empty:
                break
            conn.close()
        with self._lock:
            self._created = 0


class PostgresGatewayDb(GatewayDbBase):
    backend = "postgres"

    def __init__(
        self,
        conninfo: str,
        *,
        schema_name: str = "wf",
        use_managed_identity: bool = False,
        min_size: int = 1,
        max_size: int = 8,
    ) -> None:
        super().__init__(schema_name)
        self._use_managed_identity = use_managed_identity
        if use_managed_identity:
            self._pool: ConnectionPool | _PgPool = _PgPool(
                conninfo, use_managed_identity=True, max_size=max_size
            )
        else:
            self._pool = ConnectionPool(
                conninfo,
                min_size=min_size,
                max_size=max_size,
                kwargs={"row_factory": dict_row},
                open=True,
            )

    @contextmanager
    def _connection(self) -> Generator[psycopg.Connection, None, None]:
        with self._pool.connection() as conn:
            yield conn

    def close(self) -> None:
        self._pool.close()

    def _exec_proc(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        try:
            with self._connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                conn.commit()
        except psycopg.Error as exc:
            if self._is_auth_error(exc):
                raise WorkerAuthError(str(exc)) from exc
            raise

    def _fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            with self._connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
                conn.commit()
                return list(rows)
        except psycopg.Error as exc:
            if self._is_auth_error(exc):
                raise WorkerAuthError(str(exc)) from exc
            raise

    def _fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        rows = self._fetch_all(sql, params)
        return rows[0] if rows else None

    def worker_authenticate(self, worker_id: int, worker_token: str) -> None:
        self._exec_proc(
            f"CALL {self._qual('wf_worker_authenticate')}(%s, %s)",
            (worker_id, worker_token),
        )

    def worker_request_task(
        self,
        worker_id: int,
        worker_token: str,
        capability: Optional[str],
        max_lease_seconds: int,
    ) -> dict[str, Any]:
        row = self._fetch_one(
            f"SELECT * FROM {self._qual('sp_worker_request_task')}(%s, %s, %s, %s)",
            (worker_id, worker_token, capability, max_lease_seconds),
        )
        return self._format_task_claim(row)

    def worker_submit_result(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        result_code: int,
        output_json: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        row = self._fetch_one(
            f"SELECT * FROM {self._qual('sp_worker_submit_result')}(%s, %s, %s, %s, %s)",
            (
                node_execution_id,
                worker_id,
                worker_token,
                result_code,
                json.dumps(output_json) if output_json is not None else None,
            ),
        )
        return row if row else {"accepted": False}

    def worker_heartbeat(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        extend_seconds: int,
    ) -> dict[str, int]:
        row = self._fetch_one(
            f"SELECT * FROM {self._qual('sp_worker_heartbeat')}(%s, %s, %s, %s)",
            (node_execution_id, worker_id, worker_token, extend_seconds),
        )
        return {"rows_updated": int(row["rows_updated"]) if row else 0}

    def worker_fail_task(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        error_code: int,
        error_message: Optional[str],
    ) -> None:
        self._exec_proc(
            f"CALL {self._qual('sp_worker_fail_task')}(%s, %s, %s, %s, %s)",
            (node_execution_id, worker_id, worker_token, error_code, error_message),
        )

    def create_workflow_instance(
        self,
        workflow_version_id: int,
        context_json: Optional[dict[str, Any]],
    ) -> int:
        row = self._fetch_one(
            f"SELECT id FROM {self._qual('wf_repo_create_workflow_instance')}(%s, %s)",
            (workflow_version_id, json.dumps(context_json or {})),
        )
        if not row:
            raise RuntimeError("wf_repo_create_workflow_instance returned no id")
        return int(row["id"])

    def start_workflow_instance(self, instance_id: int) -> None:
        self._exec_proc(
            f"CALL {self._qual('sp_start_workflow_instance')}(%s)",
            (instance_id,),
        )

    def get_workflow_instance(self, instance_id: int) -> dict[str, Any]:
        row = self._fetch_one(
            f"SELECT id, workflow_version_id, status FROM {self._qual('wf_repo_get_workflow_instance')}(%s)",
            (instance_id,),
        )
        if not row:
            raise KeyError(f"instance {instance_id} not found")
        return row

    def delete_workflow_definition(self, name: str, delete_instances: bool) -> dict[str, int]:
        row = self._fetch_one(
            f"SELECT * FROM {self._qual('sp_delete_workflow_def')}(NULL, %s, %s)",
            (name, delete_instances),
        )
        if not row:
            return {"deleted_instance_count": 0, "deleted_version_count": 0}
        return {
            "deleted_instance_count": int(row["deleted_instance_count"]),
            "deleted_version_count": int(row["deleted_version_count"]),
        }

    def apply_validation_plan(
        self,
        workflow_instance_id: int,
        context_json: dict[str, Any],
        *,
        persist_extension: bool = True,
    ) -> None:
        self._exec_proc(
            f"CALL {self._qual('wf_apply_validation_plan')}(%s, %s, %s)",
            (workflow_instance_id, json.dumps(context_json), persist_extension),
        )

    def list_workflow_actions(self) -> list[dict[str, Any]]:
        rows = self._fetch_all(f"SELECT * FROM {self._qual('wf_repo_list_actions')}()")
        return [self._format_action_row(row) for row in rows]

    def get_action_schema(self, action_name: str, direction: str) -> dict[str, Any]:
        if direction not in ("input", "output"):
            raise ValueError("direction must be 'input' or 'output'")
        row = self._fetch_one(
            f"SELECT * FROM {self._qual('wf_repo_get_action_schema')}(%s, %s)",
            (action_name, direction),
        )
        if not row:
            raise KeyError(f"schema not found for action={action_name!r} direction={direction!r}")
        return self._format_schema_row(row)

    def upsert_workflow_action(
        self,
        action_name: str,
        capability: Optional[str],
        payload_schema_ref: Optional[str] = None,
    ) -> None:
        self._exec_proc(
            f"CALL {self._qual('wf_repo_upsert_workflow_action')}(%s, %s, %s)",
            (action_name, capability, payload_schema_ref),
        )

    def upsert_action_schema(
        self,
        action_name: str,
        direction: str,
        schema_json: dict[str, Any],
        schema_id: Optional[str] = None,
    ) -> None:
        if direction not in ("input", "output"):
            raise ValueError("direction must be 'input' or 'output'")
        self._exec_proc(
            f"CALL {self._qual('wf_repo_upsert_action_schema')}(%s, %s, %s::jsonb, %s)",
            (action_name, direction, json.dumps(schema_json), schema_id),
        )

    def create_workflow_definition(self, spec: dict[str, Any]) -> dict[str, Any]:
        row = self._fetch_one(
            f"SELECT {self._qual('wf_repo_create_workflow_graph')}(%s) AS payload",
            (json.dumps(spec),),
        )
        if not row or row.get("payload") is None:
            raise RuntimeError("wf_repo_create_workflow_graph returned no result")
        payload = parse_json_value(row["payload"])
        if not isinstance(payload, dict):
            raise RuntimeError("wf_repo_create_workflow_graph returned invalid payload")
        return {
            "workflow_def_id": int(payload["workflow_def_id"]),
            "workflow_version_id": int(payload["workflow_version_id"]),
            "root_node_id": int(payload["root_node_id"]),
            "name": payload.get("name"),
        }

    def get_worker_cluster_security(self, worker_id: int) -> Optional[dict[str, Any]]:
        return self._fetch_one(
            f"""
            SELECT c.allowed_source_cidrs, c.entra_client_id
            FROM {self._qual('worker')} AS w
            INNER JOIN {self._qual('cluster')} AS c ON c.id = w.cluster_id
            WHERE w.id = %s
            """,
            (worker_id,),
        )
