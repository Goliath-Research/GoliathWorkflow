#!/usr/bin/env python3
"""
OpenAPI workflow REST gateway backed by PostgreSQL wf contract objects.

Implements contracts/openapi.yaml for CI parity and reference workers on Linux.
The Delphi MethylWfGateway Windows service (WfEngineSrv, DMVC-based) provides the
same routes against UniDAC (MSSQL or PG).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db_client import (
    apply_validation_plan,
    create_workflow_instance,
    delete_workflow_definition,
    get_action_schema,
    get_workflow_instance,
    list_workflow_actions,
    pg_dsn,
    start_workflow_instance,
    worker_authenticate,
    worker_fail_task,
    worker_heartbeat,
    worker_request_task,
    worker_submit_result,
)


class RestGateway:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def dispatch(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
        query: Optional[dict[str, list[str]]] = None,
    ) -> tuple[int, Any]:
        q = query or {}

        if method == "GET" and path == "/v1/actions":
            return 200, {"actions": list_workflow_actions(self.dsn)}

        m = re.fullmatch(r"/v1/actions/([^/]+)/schema", path)
        if method == "GET" and m:
            action_name = m.group(1)
            direction = (q.get("direction") or ["input"])[0]
            try:
                return 200, get_action_schema(self.dsn, action_name, direction)
            except KeyError as exc:
                return 404, {"error": str(exc)}

        if method == "POST" and path == "/v1/workers/authenticate":
            worker_authenticate(self.dsn, int(body["worker_id"]), str(body["worker_token"]))
            return 200, {}

        if method == "POST" and path == "/v1/workers/tasks/request":
            result = worker_request_task(
                self.dsn,
                int(body["worker_id"]),
                str(body["worker_token"]),
                body.get("capability"),
                int(body.get("max_lease_seconds", 300)),
            )
            return 200, result

        m = re.fullmatch(r"/v1/workers/tasks/(\d+)/submit", path)
        if method == "POST" and m:
            ne_id = int(m.group(1))
            payload = worker_submit_result(
                self.dsn,
                ne_id,
                int(body["worker_id"]),
                str(body["worker_token"]),
                int(body["result_code"]),
                body.get("output_json"),
            )
            return 200, payload

        m = re.fullmatch(r"/v1/workers/tasks/(\d+)/heartbeat", path)
        if method == "POST" and m:
            payload = worker_heartbeat(
                self.dsn,
                int(m.group(1)),
                int(body["worker_id"]),
                str(body["worker_token"]),
                int(body.get("extend_seconds", 300)),
            )
            return 200, payload

        m = re.fullmatch(r"/v1/workers/tasks/(\d+)/fail", path)
        if method == "POST" and m:
            worker_fail_task(
                self.dsn,
                int(m.group(1)),
                int(body["worker_id"]),
                str(body["worker_token"]),
                int(body["error_code"]),
                body.get("error_message"),
            )
            return 204, None

        if method == "POST" and path == "/v1/validation/plan-iterations":
            from methyl_validation.workflow_planner import plan_validation_context

            context = plan_validation_context(body)
            instance_id = body.get("workflow_instance_id")
            if instance_id is not None:
                apply_validation_plan(
                    self.dsn,
                    int(instance_id),
                    context,
                    persist_extension=bool(body.get("persist_extension", True)),
                )
            return 200, {
                "context_json": context,
                "n_iterations": len(context.get("iterations", [])),
            }

        if method == "POST" and path == "/v1/workflows/instances":
            instance_id = create_workflow_instance(
                self.dsn,
                int(body["workflow_version_id"]),
                body.get("context_json"),
            )
            start_workflow_instance(self.dsn, instance_id)
            summary = get_workflow_instance(self.dsn, instance_id)
            return 201, summary

        m = re.fullmatch(r"/v1/workflows/instances/(\d+)", path)
        if method == "GET" and m:
            summary = get_workflow_instance(self.dsn, int(m.group(1)))
            return 200, summary

        m = re.fullmatch(r"/v1/workflows/instances/(\d+)/start", path)
        if method == "POST" and m:
            start_workflow_instance(self.dsn, int(m.group(1)))
            return 200, get_workflow_instance(self.dsn, int(m.group(1)))

        m = re.fullmatch(r"/v1/workflows/definitions/([^/]+)", path)
        if method == "DELETE" and m:
            payload = delete_workflow_definition(
                self.dsn,
                m.group(1),
                bool(body.get("delete_instances", True)),
            )
            return 200, payload

        return 404, {"error": "not found", "path": path}


def make_handler(gateway: RestGateway) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def _send(self, status: int, payload: Any) -> None:
            if status == 204:
                self.send_response(204)
                self.end_headers()
                return
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            try:
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                status, payload = gateway.dispatch("GET", parsed.path, {}, query)
                self._send(status, payload)
            except KeyError as exc:
                self._send(404, {"error": str(exc)})
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
            except Exception as exc:
                self._send(500, {"error": str(exc)})

        def do_POST(self) -> None:
            try:
                body = self._read_json()
                status, payload = gateway.dispatch("POST", self.path.split("?", 1)[0], body)
                self._send(status, payload)
            except KeyError as exc:
                self._send(400, {"error": f"missing field: {exc}"})
            except Exception as exc:
                self._send(500, {"error": str(exc)})

        def do_DELETE(self) -> None:
            try:
                parsed = urlparse(self.path)
                delete_instances = True
                if "deleteInstances" in parse_qs(parsed.query):
                    delete_instances = parse_qs(parsed.query)["deleteInstances"][0].lower() == "true"
                status, payload = gateway.dispatch(
                    "DELETE", parsed.path, {"delete_instances": delete_instances}
                )
                self._send(status, payload)
            except Exception as exc:
                self._send(500, {"error": str(exc)})

    return Handler


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MethylPipeline workflow REST gateway (PostgreSQL)")
    parser.add_argument("--host", default=os.environ.get("REST_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("REST_PORT", "8080")))
    parser.add_argument("--dsn", default=os.environ.get("METHYL_REST_PG_DSN", pg_dsn()))
    args = parser.parse_args(argv)

    gateway = RestGateway(args.dsn)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(gateway))
    print(f"REST gateway on http://{args.host}:{args.port}/v1 (PostgreSQL)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
