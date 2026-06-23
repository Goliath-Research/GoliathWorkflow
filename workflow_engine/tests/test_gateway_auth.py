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

    def list_workflow_definitions(
        self, *, source_filter: str | None = None
    ) -> list[dict[str, object]]:
        return []

    def get_workflow_definition_by_name(self, name: str) -> dict[str, object]:
        raise KeyError(name)


class RouteClassificationTests(unittest.TestCase):
    def test_worker_route(self) -> None:
        self.assertEqual(classify_route("POST", "/v1/workers/tasks/request"), RouteTier.WORKER)

    def test_admin_workflow_post(self) -> None:
        self.assertEqual(classify_route("POST", "/v1/workflows/instances"), RouteTier.ADMIN)

    def test_admin_catalog_seed(self) -> None:
        self.assertEqual(classify_route("POST", "/v1/admin/catalog/seed"), RouteTier.ADMIN)

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
    def test_admin_requires_bearer_when_entra_enabled(self) -> None:
        config = GatewayAuthConfig(
            require_entra=True,
            tenant_id="t",
            audience="api://test",
            admin_roles=("WorkflowEngineAdmin",),
        )
        with self.assertRaises(AuthError):
            authorize_request(
                _StubDb(),
                config,
                "POST",
                "/v1/admin/catalog/seed",
                [],
                {},
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


class _FilteringStubDb(_StubDb):
    def list_workflow_definitions(
        self, *, source_filter: str | None = None
    ) -> list[dict[str, object]]:
        rows = [
            {"name": "SamplePrep", "source": "system"},
            {"name": "CustomFlow", "source": "portal"},
        ]
        if source_filter is None:
            return rows
        return [row for row in rows if row["source"] == source_filter]


class ListDefinitionsTests(unittest.TestCase):
    def test_admin_list_definitions_forwards_source_query(self) -> None:
        gateway = RestGateway(_FilteringStubDb())
        status, payload = gateway.dispatch(
            "GET",
            "/v1/admin/workflows/definitions",
            {},
            query={"source": ["portal"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual([row["name"] for row in payload["definitions"]], ["CustomFlow"])

    def test_admin_list_definitions_rejects_invalid_source(self) -> None:
        gateway = RestGateway(_StubDb())
        status, payload = gateway.dispatch(
            "GET",
            "/v1/admin/workflows/definitions",
            {},
            query={"source": ["bogus"]},
        )
        self.assertEqual(status, 400)
        self.assertIn("source must be", payload["error"])


class AsgiEntraMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_route_401_without_jwt(self) -> None:
        config = GatewayAuthConfig(
            require_entra=True,
            tenant_id="t",
            audience="api://test",
            admin_roles=("WorkflowEngineAdmin",),
        )
        app = create_app(RestGateway(_StubDb()), auth_config=config)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/admin/catalog/seed", json={"catalog": {"actions": []}})
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
