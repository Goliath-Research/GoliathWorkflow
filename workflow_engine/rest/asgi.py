"""ASGI entry point for the workflow REST gateway (uvicorn)."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from anyio.to_thread import run_sync

from .auth import AuthError, AuthForbidden, GatewayAuthConfig, authorize_request
from .db.base import GatewayDb, WorkerAuthError
from .gateway import RestGateway


def create_app(
    gateway: RestGateway,
    *,
    auth_config: Optional[GatewayAuthConfig] = None,
) -> Callable[..., Any]:
    """Create an ASGI application wrapping RestGateway.dispatch."""
    config = auth_config or GatewayAuthConfig.from_env()

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return

        method = scope["method"]
        path = scope["path"]
        query_string = scope.get("query_string", b"").decode("utf-8")
        from urllib.parse import parse_qs

        query = parse_qs(query_string)
        headers = scope.get("headers") or []

        body: dict[str, Any] = {}
        if method in ("POST", "DELETE", "PUT", "PATCH"):
            chunks: list[bytes] = []
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    continue
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            raw = b"".join(chunks)
            if raw:
                body = json.loads(raw.decode("utf-8"))

        if method == "DELETE" and "deleteInstances" in query:
            body["delete_instances"] = query["deleteInstances"][0].lower() == "true"

        try:
            await run_sync(
                authorize_request,
                gateway.db,
                config,
                method,
                path,
                headers,
                body,
                scope,
            )
            status, payload = await run_sync(
                gateway.dispatch,
                method,
                path,
                body,
                query,
            )
        except AuthForbidden as exc:
            status, payload = 403, {"error": exc.message}
        except AuthError as exc:
            status, payload = 401, {"error": exc.message}
        except WorkerAuthError as exc:
            status, payload = 401, {"error": str(exc)}
        except KeyError as exc:
            status = 404 if method == "GET" else 400
            payload = {
                "error": str(exc) if method == "GET" else f"missing field: {exc}",
            }
        except ValueError as exc:
            status, payload = 400, {"error": str(exc)}
        except Exception as exc:
            status, payload = 500, {"error": str(exc)}

        if status == 204:
            await send(
                {
                    "type": "http.response.start",
                    "status": 204,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b""})
            return

        response_body = json.dumps(payload).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(response_body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": response_body})

    return app


def create_app_from_db(db: GatewayDb, *, catalog_path: Optional[Any] = None) -> Callable[..., Any]:
    return create_app(RestGateway(db, catalog_path=catalog_path))
