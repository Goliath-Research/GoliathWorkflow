"""Unit tests for gateway worker route-tier authorization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

WF_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WF_ENGINE))

from rest.asgi import create_app  # noqa: E402
from rest.auth import (  # noqa: E402
    AuthForbidden,
    GatewayAuthConfig,
    RouteTier,
    authorize_request,
    classify_route,
    extract_client_ip,
)
from rest.gateway import RestGateway  # noqa: E402


class _StubDb:
    backend = "postgres"

    def close(self) -> None:
        pass

    def get_worker_cluster_security(self, worker_id: int) -> dict[str, object] | None:
        if worker_id == 42:
            return {
                "allowed_source_cidrs": ["10.0.0.0/8"],
                "entra_client_id": None,
                "arc_resource_id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.HybridCompute/machines/gpu-west-01",
            }
        return None


class RouteClassificationTests(unittest.TestCase):
    def test_worker_route(self) -> None:
        self.assertEqual(classify_route("POST", "/v1/workers/tasks/request"), RouteTier.WORKER)

    def test_unknown_is_public(self) -> None:
        self.assertEqual(classify_route("POST", "/v1/admin/catalog/seed"), RouteTier.PUBLIC)

    def test_public_health(self) -> None:
        self.assertEqual(classify_route("GET", "/v1/health"), RouteTier.PUBLIC)


class ClientIpTests(unittest.TestCase):
    def test_trusted_proxy_prefers_x_real_ip(self) -> None:
        scope = {"client": ("127.0.0.1", 0)}
        headers = [
            (b"x-forwarded-for", b"10.1.2.3, 203.0.113.9"),
            (b"x-real-ip", b"203.0.113.9"),
        ]
        ip = extract_client_ip(scope, headers, ("127.0.0.1/32",))
        self.assertEqual(ip, "203.0.113.9")


class AuthorizeRequestTests(unittest.TestCase):
    def test_worker_ip_bind_denies_wrong_cidr(self) -> None:
        config = GatewayAuthConfig(worker_ip_bind=True, trusted_proxy_cidrs=("127.0.0.1/32",))
        scope = {"client": ("127.0.0.1", 0)}
        headers = [(b"x-forwarded-for", b"203.0.113.9")]
        with self.assertRaises(AuthForbidden):
            authorize_request(
                _StubDb(),
                config,
                "POST",
                "/v1/workers/tasks/request",
                headers,
                {"worker_id": 42, "worker_token": "x"},
                scope,
            )

    def test_enroll_skips_worker_id_ip_bind(self) -> None:
        config = GatewayAuthConfig(worker_ip_bind=True, trusted_proxy_cidrs=("127.0.0.1/32",))
        scope = {"client": ("127.0.0.1", 0)}
        headers = [(b"x-real-ip", b"198.51.100.10")]
        # No worker_id yet — enroll IP check lives in wf.sp_worker_enroll.
        authorize_request(
            _StubDb(),
            config,
            "POST",
            "/v1/workers/enroll",
            headers,
            {"cluster_key": "lambda", "external_worker_key": "vm-1"},
            scope,
        )

    def test_enroll_route_is_worker_tier(self) -> None:
        self.assertEqual(classify_route("POST", "/v1/workers/enroll"), RouteTier.WORKER)


class AsgiEnrollTests(unittest.IsolatedAsyncioTestCase):
    async def test_enroll_success_returns_token(self) -> None:
        gateway = RestGateway(_StubDb())

        def _enroll(*args: object, **kwargs: object) -> int:
            return 99

        with patch("rest.gateway.worker_enroll", side_effect=_enroll):
            app = create_app(
                gateway,
                auth_config=GatewayAuthConfig(trusted_proxy_cidrs=("127.0.0.1/32",)),
            )
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/v1/workers/enroll",
                    json={"cluster_key": "lambda", "external_worker_key": "vm-1"},
                    headers={"X-Real-IP": "203.0.113.9"},
                )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["worker_id"], 99)
        self.assertEqual(body["cluster_key"], "lambda")
        self.assertEqual(body["external_worker_key"], "vm-1")
        self.assertTrue(body["worker_token"])

    async def test_enroll_forbidden_maps_403(self) -> None:
        from rest.db.base import WorkerEnrollError

        gateway = RestGateway(_StubDb())

        def _boom(*args: object, **kwargs: object) -> int:
            raise WorkerEnrollError("client IP does not match preregistered enrollment IP.")

        with patch("rest.gateway.worker_enroll", side_effect=_boom):
            app = create_app(gateway)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/v1/workers/enroll",
                    json={"cluster_key": "lambda", "external_worker_key": "vm-1"},
                )
        self.assertEqual(response.status_code, 403)
        self.assertIn("does not match", response.json()["error"])


class AsgiEntraMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_route_404_without_handler(self) -> None:
        config = GatewayAuthConfig(require_entra=True, tenant_id="t", audience="api://test")
        app = create_app(RestGateway(_StubDb()), auth_config=config)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/admin/catalog/seed", json={"catalog": {"actions": []}})
        self.assertEqual(response.status_code, 404)

    async def test_worker_route_allowed_without_jwt(self) -> None:
        config = GatewayAuthConfig(require_entra=True, tenant_id="t", audience="api://test")
        gateway = RestGateway(_StubDb())

        def _noop(*args: object, **kwargs: object) -> None:
            return None

        with patch("rest.gateway.worker_authenticate", side_effect=_noop):
            app = create_app(gateway, auth_config=config)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/v1/workers/authenticate",
                    json={"worker_id": 1, "worker_token": "tok"},
                )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
