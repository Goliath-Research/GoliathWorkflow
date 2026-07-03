#!/usr/bin/env python3
"""
OpenAPI workflow REST gateway backed by wf contract stored procedures.

Two gateway identities:
- WORKER (/v1/workers/*): task claim/submit for compute workers
- ADMIN (/v1/admin/* + legacy CI aliases): catalog seed, workflow deploy

The gateway is domain-agnostic: no pipeline knowledge, no catalog files on disk,
and no config resolution at task claim. Use methyl-study-start for compile/plan/start.

Portal (EpiPortal) never uses this HTTP surface — it talks to Azure SQL directly.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "rest"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract"))

from .admin_handlers import (
    deploy_workflow_definition,
    get_workflow_definition_by_name,
    list_workflow_definitions,
    seed_action_catalog,
)
from .connection import resolve_connection_config
from .db import open_gateway_db
from .db.base import GatewayDb, WorkerAuthError
from .db_client import (
    create_workflow_definition,
    create_workflow_instance,
    delete_workflow_definition,
    get_action_schema,
    get_workflow_instance,
    list_workflow_actions,
    start_workflow_instance,
    upsert_action_schema,
    upsert_workflow_action,
    worker_authenticate,
    worker_fail_task,
    worker_heartbeat,
    worker_request_task,
    worker_submit_result,
)
from workflow_definition_spec import WorkflowDefinitionSpec


class RestGateway:
    def __init__(self, db: GatewayDb) -> None:
        self.db = db

    @property
    def backend(self) -> str:
        return self.db.backend

    def dispatch(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
        query: Optional[dict[str, list[str]]] = None,
    ) -> tuple[int, Any]:
        q = query or {}

        if method == "GET" and path in ("/", "/v1", "/v1/health"):
            return 200, {
                "status": "ok",
                "service": "methyl-workflow-gateway",
                "backend": self.backend,
                "api_base": "/v1",
                "identities": ["worker", "admin"],
            }

        # --- Worker tier ---
        if method == "POST" and path == "/v1/workers/authenticate":
            worker_authenticate(self.db, int(body["worker_id"]), str(body["worker_token"]))
            return 200, {}

        if method == "POST" and path == "/v1/workers/tasks/request":
            result = worker_request_task(
                self.db,
                int(body["worker_id"]),
                str(body["worker_token"]),
                body.get("capability"),
                int(body.get("max_lease_seconds", 300)),
            )
            return 200, result

        m = re.fullmatch(r"/v1/workers/tasks/(\d+)/submit", path)
        if method == "POST" and m:
            payload = worker_submit_result(
                self.db,
                int(m.group(1)),
                int(body["worker_id"]),
                str(body["worker_token"]),
                int(body["result_code"]),
                body.get("output_json"),
            )
            return 200, payload

        m = re.fullmatch(r"/v1/workers/tasks/(\d+)/heartbeat", path)
        if method == "POST" and m:
            payload = worker_heartbeat(
                self.db,
                int(m.group(1)),
                int(body["worker_id"]),
                str(body["worker_token"]),
                int(body.get("extend_seconds", 300)),
            )
            return 200, payload

        m = re.fullmatch(r"/v1/workers/tasks/(\d+)/fail", path)
        if method == "POST" and m:
            worker_fail_task(
                self.db,
                int(m.group(1)),
                int(body["worker_id"]),
                str(body["worker_token"]),
                int(body["error_code"]),
                body.get("error_message"),
            )
            return 204, None

        # --- Admin tier (/v1/admin/*) ---
        if method == "POST" and path == "/v1/admin/catalog/seed":
            payload = seed_action_catalog(
                self.db,
                body,
                upsert_workflow_action=upsert_workflow_action,
                upsert_action_schema=upsert_action_schema,
            )
            return 200, payload

        m = re.fullmatch(r"/v1/admin/actions/([^/]+)/schema", path)
        if method == "PUT" and m:
            upsert_action_schema(
                self.db,
                m.group(1),
                str(body["direction"]),
                dict(body["schema_json"]),
                body.get("schema_id"),
            )
            return 200, {"action_name": m.group(1), "direction": body["direction"]}

        if method == "POST" and path == "/v1/admin/workflows/definitions/deploy":
            result = deploy_workflow_definition(
                self.db,
                body,
                create_workflow_definition=create_workflow_definition,
                delete_workflow_definition=delete_workflow_definition,
            )
            return 201, result

        if method == "GET" and path == "/v1/admin/workflows/definitions":
            source_values = q.get("source") or []
            source = source_values[0] if source_values else None
            try:
                return 200, list_workflow_definitions(self.db, source=source)
            except ValueError as exc:
                return 400, {"error": str(exc)}

        m = re.fullmatch(r"/v1/admin/workflows/definitions/([^/]+)", path)
        if method == "GET" and m:
            try:
                return 200, get_workflow_definition_by_name(self.db, m.group(1))
            except KeyError as exc:
                return 404, {"error": str(exc)}

        if method == "DELETE" and m:
            payload = delete_workflow_definition(
                self.db,
                m.group(1),
                bool(body.get("delete_instances", True)),
            )
            return 200, payload

        if method == "POST" and path == "/v1/admin/actions":
            upsert_workflow_action(
                self.db,
                str(body["action_name"]),
                body.get("capability"),
                body.get("payload_schema_ref"),
                execution_mode=body.get("execution_mode"),
                cli_tool=body.get("cli_tool"),
                in_process_handler=body.get("in_process_handler"),
                argv_map=body.get("argv_map") if isinstance(body.get("argv_map"), dict) else None,
            )
            return 201, {"action_name": body["action_name"]}

        # --- Legacy admin aliases (CI smoke; portal must use DB) ---
        if method == "GET" and path == "/v1/actions":
            return 200, {"actions": list_workflow_actions(self.db)}

        m = re.fullmatch(r"/v1/actions/([^/]+)/schema", path)
        if method == "GET" and m:
            direction = (q.get("direction") or ["input"])[0]
            try:
                return 200, get_action_schema(self.db, m.group(1), direction)
            except KeyError as exc:
                return 404, {"error": str(exc)}

        if method == "POST" and path == "/v1/actions":
            upsert_workflow_action(
                self.db,
                str(body["action_name"]),
                body.get("capability"),
                body.get("payload_schema_ref"),
                execution_mode=body.get("execution_mode"),
                cli_tool=body.get("cli_tool"),
                in_process_handler=body.get("in_process_handler"),
                argv_map=body.get("argv_map") if isinstance(body.get("argv_map"), dict) else None,
            )
            return 201, {"action_name": body["action_name"]}

        if method == "POST" and path == "/v1/workflows/instances":
            instance_id = create_workflow_instance(
                self.db,
                int(body["workflow_version_id"]),
                body.get("context_json"),
            )
            start_workflow_instance(self.db, instance_id)
            summary = get_workflow_instance(self.db, instance_id)
            return 201, summary

        if method == "POST" and path == "/v1/workflows/definitions":
            result = deploy_workflow_definition(
                self.db,
                {"spec": WorkflowDefinitionSpec.model_validate(body).to_db_spec()},
                create_workflow_definition=create_workflow_definition,
                delete_workflow_definition=delete_workflow_definition,
            )
            return 201, result

        m = re.fullmatch(r"/v1/workflows/instances/(\d+)", path)
        if method == "GET" and m:
            summary = get_workflow_instance(self.db, int(m.group(1)))
            return 200, summary

        m = re.fullmatch(r"/v1/workflows/instances/(\d+)/start", path)
        if method == "POST" and m:
            start_workflow_instance(self.db, int(m.group(1)))
            return 200, get_workflow_instance(self.db, int(m.group(1)))

        m = re.fullmatch(r"/v1/workflows/definitions/([^/]+)", path)
        if method == "DELETE" and m:
            payload = delete_workflow_definition(
                self.db,
                m.group(1),
                bool(body.get("delete_instances", True)),
            )
            return 200, payload

        return 404, {"error": "not found", "path": path}


def main(argv: Optional[list[str]] = None) -> int:
    import uvicorn

    from .asgi import create_app

    parser = argparse.ArgumentParser(description="MethylPipeline workflow REST gateway")
    parser.add_argument(
        "--host",
        default=os.environ.get("WF_GATEWAY_HOST", os.environ.get("REST_HOST", "127.0.0.1")),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("WF_GATEWAY_PORT", os.environ.get("REST_PORT", "8080"))),
    )
    args = parser.parse_args(argv)

    config = resolve_connection_config()
    db = open_gateway_db(config)
    gateway = RestGateway(db)
    app = create_app(gateway)
    print(
        f"REST gateway on http://{args.host}:{args.port}/v1 (backend={gateway.backend})",
        flush=True,
    )
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    except KeyboardInterrupt:
        print("Stopped.", flush=True)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
