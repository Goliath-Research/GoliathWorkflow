"""Entra ID JWT validation and route-tier auth for the workflow REST gateway."""

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
    OPERATOR = "operator"


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
    app_roles: tuple[str, ...] = ()
    worker_ip_bind: bool = False
    trusted_proxy_cidrs: tuple[str, ...] = ("127.0.0.1/32", "::1/128")

    @classmethod
    def from_env(cls) -> GatewayAuthConfig:
        def _truthy(name: str) -> bool:
            return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")

        roles_raw = os.environ.get("GATEWAY_ENTRA_APP_ROLES", "").strip()
        roles = tuple(r.strip() for r in roles_raw.split(",") if r.strip())
        proxy_raw = os.environ.get("GATEWAY_TRUSTED_PROXY_CIDRS", "127.0.0.1/32,::1/128")
        proxies = tuple(c.strip() for c in proxy_raw.split(",") if c.strip())
        return cls(
            require_entra=_truthy("GATEWAY_REQUIRE_ENTRA"),
            tenant_id=os.environ.get("AZURE_TENANT_ID", "").strip(),
            audience=os.environ.get("GATEWAY_ENTRA_AUDIENCE", "").strip(),
            app_roles=roles,
            worker_ip_bind=_truthy("GATEWAY_WORKER_IP_BIND"),
            trusted_proxy_cidrs=proxies,
        )


_PUBLIC_GET = frozenset({"/", "/v1", "/v1/health"})
_OPERATOR_PREFIXES = (
    "/v1/studies/",
    "/v1/workflows/",
    "/v1/validation/",
)
_JWKS_CLIENT: Any = None
_JWKS_TENANT: str = ""


def classify_route(method: str, path: str) -> RouteTier:
    if path.startswith("/v1/workers/"):
        return RouteTier.WORKER
    if method == "GET" and path in _PUBLIC_GET:
        return RouteTier.PUBLIC
    if method == "POST" and path == "/v1/actions":
        return RouteTier.OPERATOR
    if method == "GET" and (
        path == "/v1/actions" or re.fullmatch(r"/v1/actions/[^/]+/schema", path)
    ):
        return RouteTier.OPERATOR
    if any(path.startswith(prefix) for prefix in _OPERATOR_PREFIXES):
        return RouteTier.OPERATOR
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

    # nginx sets X-Real-IP from $remote_addr on the upstream request (not client-controlled).
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
            # $proxy_add_x_forwarded_for appends the connecting client as the rightmost entry.
            candidate = parts[-1]
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                pass

    return direct_ip


def _bearer_token(headers: Sequence[tuple[bytes, bytes]]) -> Optional[str]:
    auth = _header_value(headers, "authorization")
    if not auth:
        return None
    match = re.match(r"Bearer\s+(.+)$", auth, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _get_jwks_client(tenant_id: str) -> Any:
    global _JWKS_CLIENT, _JWKS_TENANT
    if _JWKS_CLIENT is not None and _JWKS_TENANT == tenant_id:
        return _JWKS_CLIENT
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError(
            "PyJWT is required when GATEWAY_REQUIRE_ENTRA=1 (pip install 'PyJWT[crypto]')"
        ) from exc
    jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    _JWKS_CLIENT = jwt.PyJWKClient(jwks_url)
    _JWKS_TENANT = tenant_id
    return _JWKS_CLIENT


def validate_entra_jwt(token: str, config: GatewayAuthConfig) -> dict[str, Any]:
    if not config.tenant_id or not config.audience:
        raise AuthError("GATEWAY Entra configuration incomplete (AZURE_TENANT_ID, GATEWAY_ENTRA_AUDIENCE)")
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError("PyJWT is required when GATEWAY_REQUIRE_ENTRA=1") from exc

    issuer = f"https://login.microsoftonline.com/{config.tenant_id}/v2.0"
    jwks_client = _get_jwks_client(config.tenant_id)
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=config.audience,
        issuer=issuer,
        options={"require": ["exp", "iss", "aud"]},
    )
    if config.app_roles:
        roles = claims.get("roles") or []
        if not any(role in roles for role in config.app_roles):
            raise AuthForbidden("missing required app role")
    return claims


def _ip_in_allowed_cidrs(client_ip: str, cidrs: Sequence[str]) -> bool:
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


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
    if not _ip_in_allowed_cidrs(client_ip, cidrs):
        raise AuthForbidden(f"worker source IP {client_ip} not in cluster allowed CIDRs")


def authorize_request(
    db: GatewayDb,
    config: GatewayAuthConfig,
    method: str,
    path: str,
    headers: Sequence[tuple[bytes, bytes]],
    body: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    """Return JWT claims when Entra auth was used; None when auth not required/applied."""
    tier = classify_route(method, path)

    if tier == RouteTier.PUBLIC:
        return None

    client_ip = extract_client_ip(scope, headers, config.trusted_proxy_cidrs)

    if tier == RouteTier.WORKER:
        if config.worker_ip_bind and body.get("worker_id") is not None:
            check_worker_ip_bind(db, int(body["worker_id"]), client_ip)
        return None

    if not config.require_entra:
        return None

    token = _bearer_token(headers)
    if not token:
        raise AuthError("Bearer token required")
    return validate_entra_jwt(token, config)
