#!/usr/bin/env python3
"""
OpenAPI workflow REST gateway backed by wf contract stored procedures.

Worker-only identity: ``/v1/workers/*`` for task claim/submit. Catalog seed,
workflow deploy, and study lifecycle use direct DB (``workflow_engine/ops``),
portal SQL, or Cursor MCP — not this HTTP surface.

The gateway is domain-agnostic: no pipeline knowledge, no catalog files on disk,
and no config resolution at task claim.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any, Optional

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "rest"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contract"))

from .connection import resolve_connection_config
from .db import open_gateway_db
from .db.base import GatewayDb
from .db_client import (
    worker_authenticate,
    worker_enroll,
    worker_fail_task,
    worker_heartbeat,
    worker_request_task,
    worker_submit_result,
)


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
        *,
        client_ip: Optional[str] = None,
    ) -> tuple[int, Any]:
        _ = query  # worker routes do not use query params today

        if method == "GET" and path in ("/", "/v1", "/v1/health"):
            return 200, {
                "status": "ok",
                "service": "methyl-workflow-gateway",
                "backend": self.backend,
                "api_base": "/v1",
                "identities": ["worker"],
            }

        if method == "POST" and path == "/v1/workers/enroll":
            # Client IP must come from extract_client_ip (ASGI/proxy), never from the body.
            ip = (client_ip or "").strip()
            if not ip:
                return 400, {"error": "client IP unavailable; enroll requires proxy-derived client address"}
            token = secrets.token_hex(32)
            caps = body.get("capabilities")
            if caps is not None and not isinstance(caps, list):
                return 400, {"error": "capabilities must be a JSON array"}
            worker_id = worker_enroll(
                self.db,
                cluster_key=str(body["cluster_key"]),
                external_worker_key=str(body["external_worker_key"]),
                client_ip=ip,
                worker_token=token,
                capabilities=caps,
                arc_resource_id=(
                    str(body["arc_resource_id"]) if body.get("arc_resource_id") else None
                ),
            )
            return 200, {
                "worker_id": worker_id,
                "worker_token": token,
                "external_worker_key": str(body["external_worker_key"]),
                "cluster_key": str(body["cluster_key"]),
            }

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
            try:
                from rest.execution_scope import sync_execution_scope_action_entry_after_submit

                sync_execution_scope_action_entry_after_submit(
                    self.db,
                    int(m.group(1)),
                    int(body["result_code"]),
                )
            except Exception:
                pass
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
