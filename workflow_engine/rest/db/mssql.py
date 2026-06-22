"""Azure SQL / MSSQL gateway database backend (pyodbc)."""

from __future__ import annotations

import json
import queue
import threading
from contextlib import contextmanager
from typing import Any, Generator, Optional

import pyodbc

from .base import GatewayDbBase, WorkerAuthError, row_to_dict

# Required for pyodbc anonymous batches that read OUTPUT params via a trailing SELECT.
_MSSQL_OUTPUT_BATCH_PREFIX = "SET NOCOUNT ON;\n"


class _OdbcPool:
    def __init__(
        self,
        conn_str: str,
        *,
        use_managed_identity: bool = False,
        max_size: int = 8,
    ) -> None:
        self._conn_str = conn_str
        self._use_managed_identity = use_managed_identity
        self._max_size = max_size
        self._pool: queue.Queue[pyodbc.Connection] = queue.Queue(maxsize=max_size)
        self._lock = threading.Lock()
        self._created = 0

    def _new_connection(self) -> pyodbc.Connection:
        if self._use_managed_identity:
            from ..azure_auth import mssql_access_token_bytes

            token_bytes = mssql_access_token_bytes()
            return pyodbc.connect(
                self._conn_str,
                autocommit=False,
                attrs_before={1256: token_bytes},
            )
        return pyodbc.connect(self._conn_str, autocommit=False)

    @contextmanager
    def connection(self) -> Generator[pyodbc.Connection, None, None]:
        conn: Optional[pyodbc.Connection] = None
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


class MssqlGatewayDb(GatewayDbBase):
    backend = "mssql"

    def __init__(
        self,
        conn_str: str,
        *,
        schema_name: str = "wf",
        use_managed_identity: bool = False,
        max_size: int = 8,
    ) -> None:
        super().__init__(schema_name)
        self._pool = _OdbcPool(
            conn_str, use_managed_identity=use_managed_identity, max_size=max_size
        )

    def close(self) -> None:
        self._pool.close()

    @contextmanager
    def _cursor(self) -> Generator[pyodbc.Cursor, None, None]:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    def _exec_proc(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        try:
            with self._cursor() as cur:
                cur.execute(sql, params)
        except pyodbc.Error as exc:
            if self._is_auth_error(exc):
                raise WorkerAuthError(str(exc)) from exc
            raise

    def _fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            with self._cursor() as cur:
                cur.execute(sql, params)
                rows: list[dict[str, Any]] = []
                while True:
                    if cur.description is not None:
                        columns = [col[0] for col in cur.description]
                        rows = [row_to_dict(columns, row) for row in cur.fetchall()]
                    if not cur.nextset():
                        break
                return rows
        except pyodbc.Error as exc:
            if self._is_auth_error(exc):
                raise WorkerAuthError(str(exc)) from exc
            raise

    def _fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
        rows = self._fetch_all(sql, params)
        return rows[0] if rows else None

    def worker_authenticate(self, worker_id: int, worker_token: str) -> None:
        self._exec_proc(
            f"EXEC {self._qual('wf_worker_authenticate')} @worker_id=?, @worker_token=?",
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
            f"EXEC {self._qual('sp_worker_request_task')} "
            "@worker_id=?, @worker_token=?, @capability=?, @max_lease_seconds=?",
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
        out_text = json.dumps(output_json) if output_json is not None else None
        sql = f"""{_MSSQL_OUTPUT_BATCH_PREFIX}
DECLARE @accepted bit, @instance_status varchar(32), @next_ready_count int;
EXEC {self._qual('sp_worker_submit_result')}
    @node_execution_id=?,
    @worker_id=?,
    @worker_token=?,
    @result_code=?,
    @output_json=?,
    @accepted=@accepted OUTPUT,
    @instance_status=@instance_status OUTPUT,
    @next_ready_count=@next_ready_count OUTPUT;
SELECT @accepted AS accepted, @instance_status AS instance_status, @next_ready_count AS next_ready_count;
"""
        row = self._fetch_one(
            sql,
            (node_execution_id, worker_id, worker_token, result_code, out_text),
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
            f"EXEC {self._qual('sp_worker_heartbeat')} "
            "@node_execution_id=?, @worker_id=?, @worker_token=?, @extend_seconds=?",
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
            f"EXEC {self._qual('sp_worker_fail_task')} "
            "@node_execution_id=?, @worker_id=?, @worker_token=?, @error_code=?, @error_message=?",
            (node_execution_id, worker_id, worker_token, error_code, error_message),
        )

    def create_workflow_instance(
        self,
        workflow_version_id: int,
        context_json: Optional[dict[str, Any]],
    ) -> int:
        ctx = json.dumps(context_json or {})
        row = self._fetch_one(
            f"EXEC {self._qual('wf_repo_create_workflow_instance')} @version_id=?, @context_json=?",
            (workflow_version_id, ctx),
        )
        if not row:
            raise RuntimeError("wf_repo_create_workflow_instance returned no id")
        return int(row["id"])

    def start_workflow_instance(self, instance_id: int) -> None:
        self._exec_proc(
            f"EXEC {self._qual('sp_start_workflow_instance')} @workflow_instance_id=?",
            (instance_id,),
        )

    def get_workflow_instance(self, instance_id: int) -> dict[str, Any]:
        row = self._fetch_one(
            f"EXEC {self._qual('wf_repo_get_workflow_instance')} @instance_id=?",
            (instance_id,),
        )
        if not row:
            raise KeyError(f"instance {instance_id} not found")
        return row

    def delete_workflow_definition(self, name: str, delete_instances: bool) -> dict[str, int]:
        sql = f"""{_MSSQL_OUTPUT_BATCH_PREFIX}
DECLARE @deleted_instance_count int, @deleted_version_count int;
EXEC {self._qual('sp_delete_workflow_def')}
    @workflow_def_id=?,
    @workflow_name=?,
    @delete_instances=?,
    @deleted_instance_count=@deleted_instance_count OUTPUT,
    @deleted_version_count=@deleted_version_count OUTPUT;
SELECT @deleted_instance_count AS deleted_instance_count,
       @deleted_version_count AS deleted_version_count;
"""
        row = self._fetch_one(sql, (None, name, 1 if delete_instances else 0))
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
            f"EXEC {self._qual('wf_apply_validation_plan')} "
            "@workflow_instance_id=?, @context_json=CAST(? AS json), @persist_extension=?",
            (workflow_instance_id, json.dumps(context_json), 1 if persist_extension else 0),
        )

    def list_workflow_actions(self) -> list[dict[str, Any]]:
        rows = self._fetch_all(f"SELECT * FROM {self._qual('wf_repo_list_actions')}()")
        return [self._format_action_row(row) for row in rows]

    def get_action_schema(self, action_name: str, direction: str) -> dict[str, Any]:
        if direction not in ("input", "output"):
            raise ValueError("direction must be 'input' or 'output'")
        row = self._fetch_one(
            f"SELECT * FROM {self._qual('wf_repo_get_action_schema')}(?, ?)",
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
            f"EXEC {self._qual('wf_repo_upsert_workflow_action')} "
            "@action_name=?, @capability=?, @payload_schema_ref=?",
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
            f"EXEC {self._qual('wf_repo_upsert_action_schema')} "
            "@action_name=?, @direction=?, @schema_json=CAST(? AS json), @schema_id=?",
            (action_name, direction, json.dumps(schema_json), schema_id),
        )

    def create_workflow_definition(self, spec: dict[str, Any]) -> dict[str, Any]:
        row = self._fetch_one(
            f"EXEC {self._qual('wf_repo_create_workflow_graph')} @spec=CAST(? AS json)",
            (json.dumps(spec),),
        )
        if not row:
            raise RuntimeError("wf_repo_create_workflow_graph returned no result")
        return {
            "workflow_def_id": int(row["workflow_def_id"]),
            "workflow_version_id": int(row["workflow_version_id"]),
            "root_node_id": int(row["root_node_id"]),
            "name": row.get("name"),
        }
