"""ASGI-level tests for the workflow REST gateway."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

WF_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WF_ENGINE))

from rest.asgi import create_app  # noqa: E402
from rest.db.base import WorkerAuthError  # noqa: E402
from rest.gateway import RestGateway  # noqa: E402


class _StubDb:
    backend = "postgres"

    def close(self) -> None:
        pass


class AsgiGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_route(self) -> None:
        app = create_app(RestGateway(_StubDb()))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/v1/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["backend"], "postgres")

    async def test_worker_auth_error_returns_401(self) -> None:
        gateway = RestGateway(_StubDb())

        def _raise_auth(*args: object, **kwargs: object) -> None:
            raise WorkerAuthError("invalid token")

        with patch("rest.gateway.worker_authenticate", side_effect=_raise_auth):
            app = create_app(gateway)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/v1/workers/authenticate",
                    json={"worker_id": 1, "worker_token": "bad"},
                )
        self.assertEqual(response.status_code, 401)
        self.assertIn("invalid token", response.json()["error"])


if __name__ == "__main__":
    unittest.main()
