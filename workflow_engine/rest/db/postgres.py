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
from .base import GatewayDbBase, WorkerAuthError, WorkerEnrollError, parse_json_value


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

    def worker_enroll(
        self,
        *,
        cluster_key: str,
        external_worker_key: str,
        client_ip: str,
        worker_token: str,
        capabilities: Optional[list[Any]] = None,
        arc_resource_id: Optional[str] = None,
    ) -> int:
        import hashlib

        token_hash_hex = hashlib.sha256(worker_token.encode("utf-8")).hexdigest()
        caps = json.dumps(capabilities if capabilities is not None else [])
        try:
            row = self._fetch_one(
                f"""
                SELECT worker_id FROM {self._qual('sp_worker_enroll')}(
                    %s, %s, %s, %s, %s::jsonb, %s
                )
                """,
                (
                    cluster_key,
                    external_worker_key,
                    client_ip,
                    token_hash_hex,
                    caps,
                    arc_resource_id,
                ),
            )
        except Exception as exc:
            if self._is_enroll_forbidden(exc):
                raise WorkerEnrollError(str(exc), forbidden=True) from exc
            raise
        if not row or row.get("worker_id") is None:
            raise WorkerEnrollError("worker enroll failed", forbidden=False)
        return int(row["worker_id"])

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
    ) -> dict[str, Any]:
        row = self._fetch_one(
            f"SELECT * FROM {self._qual('sp_worker_heartbeat')}(%s, %s, %s, %s)",
            (node_execution_id, worker_id, worker_token, extend_seconds),
        )
        if not row:
            return {"rows_updated": 0, "desired_state": "ACTIVE", "command": "NONE"}
        return {
            "rows_updated": int(row["rows_updated"] or 0),
            "desired_state": str(row.get("desired_state") or "ACTIVE"),
            "command": str(row.get("command") or "NONE"),
        }

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

    def apply_execution_scope(
        self,
        workflow_instance_id: int,
        *,
        set_key: str,
        display_name: Optional[str] = None,
        config_json: Optional[dict[str, Any]] = None,
        persist_extension: bool = True,
    ) -> None:
        self._exec_proc(
            f"CALL {self._qual('wf_apply_execution_scope')}(%s, %s, %s, %s, %s)",
            (
                workflow_instance_id,
                set_key,
                display_name,
                json.dumps(config_json or {}),
                persist_extension,
            ),
        )

    def get_action_submit_context(self, node_execution_id: int) -> Optional[dict[str, Any]]:
        row = self._fetch_one(
            f"SELECT * FROM {self._qual('wf_repo_get_action_submit_context')}(%s)",
            (node_execution_id,),
        )
        if not row:
            return None
        return {
            "workflow_instance_id": row["workflow_instance_id"],
            "execution_scope_key": row.get("execution_scope_key"),
            "action_name": row.get("action_name"),
            "input_json": parse_json_value(row.get("input_json")) or {},
        }

    def upsert_execution_scope_action_entry(
        self,
        *,
        set_key: str,
        workflow_instance_id: int,
        action_name: str,
        run_key: str,
        content_key: str,
    ) -> None:
        self._exec_proc(
            f"CALL {self._qual('wf_repo_upsert_execution_scope_action_entry')}(%s, %s, %s, %s, %s)",
            (set_key, workflow_instance_id, action_name, run_key, content_key),
        )

    def start_hyperparam_search(
        self,
        *,
        study_row_id: Optional[int] = None,
        display_name: Optional[str] = None,
        grid_json: Optional[dict[str, Any]] = None,
        objective_json: Optional[dict[str, Any]] = None,
        base_context_hash: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> int:
        row = self._fetch_one(
            "SELECT portal.sp_start_hyperparam_grid(%s, %s, %s::jsonb, %s::jsonb, %s, %s) AS search_id",
            (
                study_row_id,
                display_name,
                json.dumps(grid_json or {}),
                json.dumps(objective_json or {}),
                base_context_hash,
                created_by,
            ),
        )
        if not row or row.get("search_id") is None:
            raise RuntimeError("portal.sp_start_hyperparam_grid returned no search_id")
        return int(row["search_id"])

    def add_hyperparam_trial(
        self,
        *,
        search_id: int,
        trial_index: int,
        overrides_json: Optional[dict[str, Any]] = None,
        workflow_instance_id: Optional[int] = None,
        execution_scope_key: Optional[str] = None,
    ) -> None:
        self._exec_proc(
            "CALL portal.sp_add_hyperparam_trial(%s, %s, %s::jsonb, %s, %s)",
            (
                search_id,
                trial_index,
                json.dumps(overrides_json or {}),
                workflow_instance_id,
                execution_scope_key,
            ),
        )

    def score_hyperparam_trial(
        self,
        *,
        search_id: int,
        trial_index: int,
        objective: Optional[float] = None,
        feasible: Optional[bool] = None,
        result_json: Optional[dict[str, Any]] = None,
    ) -> None:
        self._exec_proc(
            "CALL portal.sp_score_hyperparam_trial(%s, %s, %s, %s, %s::jsonb)",
            (
                search_id,
                trial_index,
                objective,
                feasible,
                json.dumps(result_json) if result_json is not None else None,
            ),
        )

    def get_hyperparam_search(self, search_id: int) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            f"SELECT * FROM portal.sp_get_hyperparam_search(%s)",
            (search_id,),
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "search_id": r.get("search_id"),
                    "search_status": r.get("search_status"),
                    "trial_index": r.get("trial_index"),
                    "overrides_json": parse_json_value(r.get("overrides_json")),
                    "workflow_instance_id": r.get("workflow_instance_id"),
                    "execution_scope_key": r.get("execution_scope_key"),
                    "instance_status": r.get("instance_status"),
                    "trial_status": r.get("trial_status"),
                    "objective": r.get("objective"),
                    "feasible": r.get("feasible"),
                }
            )
        return out

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
        *,
        execution_mode: Optional[str] = None,
        cli_tool: Optional[str] = None,
        in_process_handler: Optional[str] = None,
        argv_map: Optional[dict[str, Any]] = None,
        max_per_worker: Optional[int] = None,
        exclusive_worker: bool = False,
        affinity_key_field: Optional[str] = None,
        prefer_previous_worker: bool = False,
        prefer_continue_group: bool = False,
    ) -> None:
        self._exec_proc(
            f"CALL {self._qual('wf_repo_upsert_workflow_action')}"
            "(%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)",
            (
                action_name,
                capability,
                payload_schema_ref,
                execution_mode,
                cli_tool,
                in_process_handler,
                json.dumps(argv_map) if argv_map is not None else None,
                max_per_worker,
                exclusive_worker,
                affinity_key_field,
                prefer_previous_worker,
                prefer_continue_group,
            ),
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

    def list_workflow_definitions(
        self, *, source_filter: Optional[str] = None
    ) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            f"""
            SELECT wd.id AS workflow_def_id,
                   wd.name,
                   COALESCE(wd.source, 'system') AS source,
                   wv.id AS workflow_version_id,
                   wv.version_major,
                   wv.version_minor
            FROM {self._qual('workflow_def')} wd
            LEFT JOIN LATERAL (
                SELECT id, version_major, version_minor
                FROM {self._qual('workflow_version')}
                WHERE workflow_def_id = wd.id AND is_active = true
                ORDER BY version_major DESC, version_minor DESC
                LIMIT 1
            ) wv ON true
            WHERE (%s IS NULL OR COALESCE(wd.source, 'system') = %s)
            ORDER BY wd.name
            """,
            (source_filter, source_filter),
        )
        return rows

    def get_workflow_definition_by_name(self, name: str) -> dict[str, Any]:
        row = self._fetch_one(
            f"""
            SELECT wd.id AS workflow_def_id,
                   wd.name,
                   wd.description,
                   COALESCE(wd.source, 'system') AS source,
                   wv.id AS workflow_version_id,
                   wv.version_major,
                   wv.version_minor
            FROM {self._qual('workflow_def')} wd
            LEFT JOIN LATERAL (
                SELECT id, version_major, version_minor
                FROM {self._qual('workflow_version')}
                WHERE workflow_def_id = wd.id AND is_active = true
                ORDER BY version_major DESC, version_minor DESC
                LIMIT 1
            ) wv ON true
            WHERE wd.name = %s
            """,
            (name,),
        )
        if not row:
            raise KeyError(f"workflow definition not found: {name!r}")
        return row

    def get_worker_cluster_security(self, worker_id: int) -> Optional[dict[str, Any]]:
        return self._fetch_one(
            f"""
            SELECT c.allowed_source_cidrs, c.entra_client_id, c.arc_resource_id
            FROM {self._qual('worker')} AS w
            INNER JOIN {self._qual('cluster')} AS c ON c.id = w.cluster_id
            WHERE w.id = %s
            """,
            (worker_id,),
        )
