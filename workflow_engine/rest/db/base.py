"""Shared gateway database contract and helpers."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Optional, Protocol, runtime_checkable


class WorkerAuthError(Exception):
    """Raised when wf.wf_worker_authenticate rejects credentials."""


class WorkerEnrollError(Exception):
    """Raised when wf.sp_worker_enroll rejects enroll (IP/allowlist/revoked)."""

    def __init__(self, message: str, *, forbidden: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.forbidden = forbidden


class GatewayDbError(Exception):
    """Generic database gateway failure."""


def parse_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return value
    return value


def row_to_dict(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for idx, name in enumerate(columns):
        value = row[idx]
        if name.endswith("_json") or name == "schema_json":
            out[name] = parse_json_value(value)
        else:
            out[name] = value
    return out


@runtime_checkable
class GatewayDb(Protocol):
    backend: str

    def close(self) -> None: ...

    def worker_authenticate(self, worker_id: int, worker_token: str) -> None: ...

    def worker_enroll(
        self,
        *,
        cluster_key: str,
        external_worker_key: str,
        client_ip: str,
        worker_token: str,
        capabilities: Optional[list[Any]] = None,
        arc_resource_id: Optional[str] = None,
    ) -> int: ...

    def worker_request_task(
        self,
        worker_id: int,
        worker_token: str,
        capability: Optional[str],
        max_lease_seconds: int,
    ) -> dict[str, Any]: ...

    def worker_submit_result(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        result_code: int,
        output_json: Optional[dict[str, Any]],
    ) -> dict[str, Any]: ...

    def worker_heartbeat(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        extend_seconds: int,
    ) -> dict[str, Any]: ...

    def worker_fail_task(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        error_code: int,
        error_message: Optional[str],
    ) -> None: ...

    def create_workflow_instance(
        self,
        workflow_version_id: int,
        context_json: Optional[dict[str, Any]],
    ) -> int: ...

    def start_workflow_instance(self, instance_id: int) -> None: ...

    def get_workflow_instance(self, instance_id: int) -> dict[str, Any]: ...

    def delete_workflow_definition(
        self,
        name: str,
        delete_instances: bool,
    ) -> dict[str, Any]: ...

    def apply_validation_plan(
        self,
        workflow_instance_id: int,
        context_json: dict[str, Any],
        *,
        persist_extension: bool = True,
    ) -> None: ...

    def apply_execution_scope(
        self,
        workflow_instance_id: int,
        *,
        set_key: str,
        display_name: Optional[str] = None,
        config_json: Optional[dict[str, Any]] = None,
        persist_extension: bool = True,
    ) -> None: ...

    def get_action_submit_context(
        self,
        node_execution_id: int,
    ) -> Optional[dict[str, Any]]: ...

    def upsert_execution_scope_action_entry(
        self,
        *,
        set_key: str,
        workflow_instance_id: int,
        action_name: str,
        run_key: str,
        content_key: str,
    ) -> None: ...

    def start_hyperparam_search(
        self,
        *,
        study_row_id: Optional[int] = None,
        display_name: Optional[str] = None,
        grid_json: Optional[dict[str, Any]] = None,
        objective_json: Optional[dict[str, Any]] = None,
        base_context_hash: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> int: ...

    def add_hyperparam_trial(
        self,
        *,
        search_id: int,
        trial_index: int,
        overrides_json: Optional[dict[str, Any]] = None,
        workflow_instance_id: Optional[int] = None,
        execution_scope_key: Optional[str] = None,
    ) -> None: ...

    def score_hyperparam_trial(
        self,
        *,
        search_id: int,
        trial_index: int,
        objective: Optional[float] = None,
        feasible: Optional[bool] = None,
        result_json: Optional[dict[str, Any]] = None,
    ) -> None: ...

    def get_hyperparam_search(self, search_id: int) -> list[dict[str, Any]]: ...

    def list_workflow_actions(self) -> list[dict[str, Any]]: ...

    def get_action_schema(self, action_name: str, direction: str) -> dict[str, Any]: ...

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
    ) -> None: ...

    def upsert_action_schema(
        self,
        action_name: str,
        direction: str,
        schema_json: dict[str, Any],
        schema_id: Optional[str] = None,
    ) -> None: ...

    def create_workflow_definition(self, spec: dict[str, Any]) -> dict[str, Any]: ...

    def list_workflow_definitions(
        self, *, source_filter: Optional[str] = None
    ) -> list[dict[str, Any]]: ...

    def get_workflow_definition_by_name(self, name: str) -> dict[str, Any]: ...

    def get_worker_cluster_security(self, worker_id: int) -> Optional[dict[str, Any]]: ...


class GatewayDbBase(ABC):
    backend: str

    def __init__(self, schema_name: str = "wf") -> None:
        self._schema = schema_name

    def _qual(self, name: str) -> str:
        return f"{self._schema}.{name}"

    @staticmethod
    def _is_auth_error(exc: BaseException) -> bool:
        message = str(exc).lower()
        if "invalid or unauthorized worker credentials" in message:
            return True
        if "50003" in message:
            return True
        sqlstate = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
        return sqlstate == "50003"

    @staticmethod
    def _is_enroll_forbidden(exc: BaseException) -> bool:
        message = str(exc).lower()
        markers = (
            "50053",
            "50054",
            "50055",
            "50052",
            "no enrollment allowlist",
            "does not match preregistered",
            "has been revoked",
            "unknown or disabled cluster",
        )
        return any(m in message for m in markers)

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def worker_authenticate(self, worker_id: int, worker_token: str) -> None: ...

    @abstractmethod
    def worker_enroll(
        self,
        *,
        cluster_key: str,
        external_worker_key: str,
        client_ip: str,
        worker_token: str,
        capabilities: Optional[list[Any]] = None,
        arc_resource_id: Optional[str] = None,
    ) -> int: ...

    @abstractmethod
    def worker_request_task(
        self,
        worker_id: int,
        worker_token: str,
        capability: Optional[str],
        max_lease_seconds: int,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def worker_submit_result(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        result_code: int,
        output_json: Optional[dict[str, Any]],
    ) -> dict[str, Any]: ...

    @abstractmethod
    def worker_heartbeat(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        extend_seconds: int,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def worker_fail_task(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        error_code: int,
        error_message: Optional[str],
    ) -> None: ...

    @abstractmethod
    def create_workflow_instance(
        self,
        workflow_version_id: int,
        context_json: Optional[dict[str, Any]],
    ) -> int: ...

    @abstractmethod
    def start_workflow_instance(self, instance_id: int) -> None: ...

    @abstractmethod
    def get_workflow_instance(self, instance_id: int) -> dict[str, Any]: ...

    @abstractmethod
    def delete_workflow_definition(
        self,
        name: str,
        delete_instances: bool,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def apply_validation_plan(
        self,
        workflow_instance_id: int,
        context_json: dict[str, Any],
        *,
        persist_extension: bool = True,
    ) -> None: ...

    @abstractmethod
    def list_workflow_actions(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_action_schema(self, action_name: str, direction: str) -> dict[str, Any]: ...

    @abstractmethod
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
    ) -> None: ...

    @abstractmethod
    def create_workflow_definition(self, spec: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def list_workflow_definitions(
        self, *, source_filter: Optional[str] = None
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_workflow_definition_by_name(self, name: str) -> dict[str, Any]: ...

    @abstractmethod
    def get_worker_cluster_security(self, worker_id: int) -> Optional[dict[str, Any]]: ...

    def _format_task_claim(self, row: Optional[dict[str, Any]]) -> dict[str, Any]:
        desired = "ACTIVE"
        command = "NONE"
        if row:
            desired = str(row.get("desired_state") or "ACTIVE")
            command = str(row.get("command") or "NONE")
        if not row or row.get("node_execution_id") is None:
            return {
                "has_task": False,
                "desired_state": desired,
                "command": command,
            }
        return {
            "has_task": True,
            "node_execution_id": row["node_execution_id"],
            "workflow_instance_id": row["workflow_instance_id"],
            "node_key": row["node_key"],
            "action_name": row["action_name"],
            "capability": row["capability"],
            "attempt_no": row["attempt_no"],
            "input_json": parse_json_value(row.get("input_json")) or {},
            "iteration_no": row["iteration_no"],
            "desired_state": desired,
            "command": command,
        }

    def _format_action_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_name": row["action_name"],
            "capability": row.get("capability"),
            "has_input_schema": bool(row.get("has_input_schema")),
            "has_output_schema": bool(row.get("has_output_schema")),
            "execution_mode": row.get("execution_mode"),
            "cli_tool": row.get("cli_tool"),
            "in_process_handler": row.get("in_process_handler"),
            "argv_map": parse_json_value(row.get("argv_map")),
        }

    def _format_schema_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_name": row["action_name"],
            "direction": row["direction"],
            "schema_id": row.get("schema_id"),
            "schema_json": parse_json_value(row.get("schema_json")) or {},
        }
