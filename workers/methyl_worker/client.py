"""HTTP client for the workflow middle-tier REST API (contracts/openapi.yaml)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TaskClaim:
    """One claimed READY task from POST /workers/tasks/request."""

    node_execution_id: int
    workflow_instance_id: int
    action_name: str
    capability: str
    input_json: Dict[str, Any]
    node_key: str = ""
    attempt_no: int = 1
    iteration_no: int = 0


@dataclass(frozen=True)
class SubmitAck:
    accepted: bool
    instance_status: str
    next_ready_count: int


class WorkflowRestClient:
    """REST-only workflow worker client; no direct database access."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        timeout_seconds: float = 120.0,
    ) -> None:
        raw = base_url or os.environ.get("METHYL_API_BASE", "http://localhost:8080/v1")
        self.base_url = raw.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} {path}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Request failed {path}: {exc}") from exc

    def authenticate(self, worker_id: int, worker_token: str) -> None:
        self._post_json(
            "/workers/authenticate",
            {"worker_id": worker_id, "worker_token": worker_token},
        )

    def request_task(
        self,
        worker_id: int,
        worker_token: str,
        capability: Optional[str] = None,
        *,
        max_lease_seconds: Optional[int] = None,
    ) -> Optional[TaskClaim]:
        payload: Dict[str, Any] = {
            "worker_id": worker_id,
            "worker_token": worker_token,
            "max_lease_seconds": max_lease_seconds
            or int(os.environ.get("WORKER_LEASE_SECONDS", "300")),
        }
        if capability:
            payload["capability"] = capability

        body = self._post_json("/workers/tasks/request", payload)
        if not body.get("has_task"):
            return None

        inp = body.get("input_json") or {}
        if isinstance(inp, str):
            inp = json.loads(inp) if inp else {}

        return TaskClaim(
            node_execution_id=int(body["node_execution_id"]),
            workflow_instance_id=int(body.get("workflow_instance_id") or 0),
            action_name=str(body.get("action_name") or ""),
            capability=str(body.get("capability") or ""),
            input_json=inp,
            node_key=str(body.get("node_key") or ""),
            attempt_no=int(body.get("attempt_no") or 1),
            iteration_no=int(body.get("iteration_no") or 0),
        )

    def submit_result(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        result_code: int,
        output_json: Optional[Dict[str, Any]] = None,
    ) -> SubmitAck:
        payload: Dict[str, Any] = {
            "worker_id": worker_id,
            "worker_token": worker_token,
            "result_code": result_code,
        }
        if output_json is not None:
            payload["output_json"] = output_json

        body = self._post_json(f"/workers/tasks/{node_execution_id}/submit", payload)
        return SubmitAck(
            accepted=bool(body.get("accepted", True)),
            instance_status=str(body.get("instance_status") or ""),
            next_ready_count=int(body.get("next_ready_count") or 0),
        )

    def heartbeat(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        *,
        extend_seconds: Optional[int] = None,
    ) -> int:
        body = self._post_json(
            f"/workers/tasks/{node_execution_id}/heartbeat",
            {
                "worker_id": worker_id,
                "worker_token": worker_token,
                "extend_seconds": extend_seconds
                or int(os.environ.get("WORKER_LEASE_SECONDS", "300")),
            },
        )
        return int(body.get("rows_updated") or 0)

    def fail_task(
        self,
        node_execution_id: int,
        worker_id: int,
        worker_token: str,
        error_code: int,
        error_message: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "worker_id": worker_id,
            "worker_token": worker_token,
            "error_code": error_code,
        }
        if error_message:
            payload["error_message"] = error_message
        self._post_json(f"/workers/tasks/{node_execution_id}/fail", payload)
