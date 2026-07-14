"""Worker IP / Arc attestation helpers for the workflow REST gateway.

The gateway is worker-only; catalog seed and study lifecycle use direct DB.
``GATEWAY_REQUIRE_ENTRA`` is retained for deployment compatibility but does not
gate worker routes (workers authenticate via ``worker_token``).
"""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from .db.base import GatewayDb


class RouteTier(Enum):
    PUBLIC = "public"
    WORKER = "worker"


class AuthError(Exception):
    """Authentication failure (401)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthForbidden(AuthError):
    """Authorization failure (403)."""


@dataclass(frozen=True)
class GatewayAuthConfig:
    require_entra: bool = False
    tenant_id: str = ""
    audience: str = ""
    worker_ip_bind: bool = False
    require_arc_attest: bool = False
    trusted_proxy_cidrs: tuple[str, ...] = ("127.0.0.1/32", "::1/128")

    @classmethod
    def from_env(cls) -> GatewayAuthConfig:
        def _truthy(name: str) -> bool:
            return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")

        proxy_raw = os.environ.get("GATEWAY_TRUSTED_PROXY_CIDRS", "127.0.0.1/32,::1/128")
        proxies = tuple(c.strip() for c in proxy_raw.split(",") if c.strip())
        return cls(
            require_entra=_truthy("GATEWAY_REQUIRE_ENTRA"),
            tenant_id=os.environ.get("AZURE_TENANT_ID", "").strip(),
            audience=os.environ.get("GATEWAY_ENTRA_AUDIENCE", "").strip(),
            worker_ip_bind=_truthy("GATEWAY_WORKER_IP_BIND"),
            require_arc_attest=_truthy("GATEWAY_REQUIRE_ARC_ATTEST"),
            trusted_proxy_cidrs=proxies,
        )


_PUBLIC_GET = frozenset({"/", "/v1", "/v1/health"})


def classify_route(method: str, path: str) -> RouteTier:
    if path.startswith("/v1/workers/"):
        return RouteTier.WORKER
    if method == "GET" and path in _PUBLIC_GET:
        return RouteTier.PUBLIC
    return RouteTier.PUBLIC


def _header_value(headers: Sequence[tuple[bytes, bytes]], name: str) -> Optional[str]:
    target = name.lower()
    for key, value in headers:
        if key.decode("latin-1").lower() == target:
            return value.decode("latin-1")
    return None


def _is_trusted_proxy(direct_ip: str, trusted_proxy_cidrs: Sequence[str]) -> bool:
    try:
        direct_addr = ipaddress.ip_address(direct_ip)
    except ValueError:
        return False
    for cidr in trusted_proxy_cidrs:
        try:
            if direct_addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def extract_client_ip(
    scope: Mapping[str, Any],
    headers: Sequence[tuple[bytes, bytes]],
    trusted_proxy_cidrs: Sequence[str],
) -> str:
    remote = scope.get("client")
    direct_ip = remote[0] if remote else "0.0.0.0"
    if not _is_trusted_proxy(direct_ip, trusted_proxy_cidrs):
        return direct_ip

    real_ip = _header_value(headers, "x-real-ip")
    if real_ip:
        candidate = real_ip.strip()
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            pass

    forwarded = _header_value(headers, "x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            candidate = parts[-1]
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                pass

    return direct_ip


def check_worker_ip_bind(
    db: GatewayDb,
    worker_id: int,
    client_ip: str,
) -> None:
    security = db.get_worker_cluster_security(worker_id)
    if not security:
        return
    raw = security.get("allowed_source_cidrs")
    if not raw:
        return
    if isinstance(raw, str):
        import json

        try:
            cidrs = json.loads(raw)
        except json.JSONDecodeError:
            cidrs = []
    else:
        cidrs = raw
    if not isinstance(cidrs, list) or not cidrs:
        return
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        raise AuthForbidden(f"worker source IP {client_ip} not in cluster allowed CIDRs")
    for cidr in cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return
        except ValueError:
            continue
    raise AuthForbidden(f"worker source IP {client_ip} not in cluster allowed CIDRs")


def check_worker_arc_attest(
    db: GatewayDb,
    worker_id: int,
    headers: Sequence[tuple[bytes, bytes]],
) -> None:
    security = db.get_worker_cluster_security(worker_id)
    if not security:
        return
    expected = security.get("arc_resource_id")
    if not expected:
        return
    header_val = _header_value(headers, "x-arc-resource-id")
    if not header_val or header_val.strip() != str(expected).strip():
        raise AuthForbidden("worker Arc resource id does not match cluster registration")


def authorize_request(
    db: GatewayDb,
    config: GatewayAuthConfig,
    method: str,
    path: str,
    headers: Sequence[tuple[bytes, bytes]],
    body: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    """Apply worker IP/Arc checks; return None (no JWT claims on worker-only gateway)."""
    tier = classify_route(method, path)

    if tier == RouteTier.PUBLIC:
        return None

    client_ip = extract_client_ip(scope, headers, config.trusted_proxy_cidrs)

    if tier == RouteTier.WORKER:
        # Enroll has no worker_id yet; IP allowlist is enforced inside wf.sp_worker_enroll.
        if path.rstrip("/") == "/v1/workers/enroll":
            return None
        if body.get("worker_id") is not None:
            wid = int(body["worker_id"])
            if config.worker_ip_bind:
                check_worker_ip_bind(db, wid, client_ip)
            if config.require_arc_attest:
                check_worker_arc_attest(db, wid, headers)
        return None

    return None
