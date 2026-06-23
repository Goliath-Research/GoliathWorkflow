"""Unit tests for gateway Entra / route-tier authorization."""

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
    AuthError,
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

    def test_operator_workflow_post(self) -> None:
        self.assertEqual(classify_route("POST", "/v1/workflows/instances"), RouteTier.OPERATOR)

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

    def test_trusted_proxy_uses_rightmost_forwarded_for_without_real_ip(self) -> None:
        scope = {"client": ("127.0.0.1", 0)}
        headers = [(b"x-forwarded-for", b"10.1.2.3, 203.0.113.9")]
        ip = extract_client_ip(scope, headers, ("127.0.0.1/32",))
        self.assertEqual(ip, "203.0.113.9")

    def test_trusted_proxy_ignores_spoofed_leftmost_forwarded_for(self) -> None:
        scope = {"client": ("127.0.0.1", 0)}
        headers = [
            (b"x-forwarded-for", b"10.5.0.1, 203.0.113.9"),
            (b"x-real-ip", b"203.0.113.9"),
        ]
        ip = extract_client_ip(scope, headers, ("127.0.0.1/32",))
        self.assertNotEqual(ip, "10.5.0.1")
        self.assertEqual(ip, "203.0.113.9")

    def test_untrusted_proxy_uses_direct(self) -> None:
        scope = {"client": ("203.0.113.5", 0)}
        headers = [(b"x-forwarded-for", b"10.1.2.3")]
        ip = extract_client_ip(scope, headers, ("127.0.0.1/32",))
        self.assertEqual(ip, "203.0.113.5")


class AuthorizeRequestTests(unittest.TestCase):
    def test_operator_requires_bearer_when_entra_enabled(self) -> None:
        config = GatewayAuthConfig(require_entra=True, tenant_id="t", audience="api://test")
        with self.assertRaises(AuthError):
            authorize_request(
                _StubDb(),
                config,
                "POST",
                "/v1/workflows/instances",
                [],
                {"workflow_version_id": 1},
                {"client": ("127.0.0.1", 0)},
            )

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

    def test_worker_ip_bind_allows_matching_cidr(self) -> None:
        config = GatewayAuthConfig(worker_ip_bind=True, trusted_proxy_cidrs=("127.0.0.1/32",))
        scope = {"client": ("127.0.0.1", 0)}
        headers = [
            (b"x-forwarded-for", b"10.5.0.1"),
            (b"x-real-ip", b"10.5.0.1"),
        ]
        authorize_request(
            _StubDb(),
            config,
            "POST",
            "/v1/workers/tasks/request",
            headers,
            {"worker_id": 42, "worker_token": "x"},
            scope,
        )

    def test_worker_ip_bind_rejects_spoofed_forwarded_for(self) -> None:
        config = GatewayAuthConfig(worker_ip_bind=True, trusted_proxy_cidrs=("127.0.0.1/32",))
        scope = {"client": ("127.0.0.1", 0)}
        headers = [
            (b"x-forwarded-for", b"10.5.0.1, 203.0.113.9"),
            (b"x-real-ip", b"203.0.113.9"),
        ]
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

    def test_worker_arc_attest_denies_mismatch(self) -> None:
        config = GatewayAuthConfig(require_arc_attest=True)
        headers = [(b"x-arc-resource-id", b"/subscriptions/wrong")]
        with self.assertRaises(AuthForbidden):
            authorize_request(
                _StubDb(),
                config,
                "POST",
                "/v1/workers/tasks/request",
                headers,
                {"worker_id": 42, "worker_token": "x"},
                {"client": ("10.5.0.1", 0)},
            )

    def test_worker_arc_attest_allows_match(self) -> None:
        config = GatewayAuthConfig(require_arc_attest=True)
        arc_id = b"/subscriptions/sub/resourceGroups/rg/providers/Microsoft.HybridCompute/machines/gpu-west-01"
        headers = [(b"x-arc-resource-id", arc_id)]
        authorize_request(
            _StubDb(),
            config,
            "POST",
            "/v1/workers/tasks/request",
            headers,
            {"worker_id": 42, "worker_token": "x"},
            {"client": ("10.5.0.1", 0)},
        )


class AsgiEntraMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_operator_route_401_without_jwt(self) -> None:
        config = GatewayAuthConfig(require_entra=True, tenant_id="t", audience="api://test")
        app = create_app(RestGateway(_StubDb()), auth_config=config)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/workflows/instances",
                json={"workflow_version_id": 1},
            )
        self.assertEqual(response.status_code, 401)

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
