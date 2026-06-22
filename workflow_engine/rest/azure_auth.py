"""Azure Entra ID access tokens for workflow gateway database connections."""

from __future__ import annotations

import os
import struct
import threading
import time
from dataclasses import dataclass
from typing import Optional

from .connection import DatabaseBackend

# Match Delphi WfEngine.Connection.pas GetEntraTokenResource.
_MSSQL_RESOURCE = "https://database.windows.net/.default"
_POSTGRES_RESOURCE = "https://ossrdbms-aad.database.windows.net/.default"

# Refresh before expiry (Azure tokens are typically ~1 hour).
_REFRESH_MARGIN_SECONDS = 300


@dataclass
class _CachedToken:
    token: str
    expires_on: float


_lock = threading.Lock()
_cache: dict[str, _CachedToken] = {}


def _token_scope(backend: DatabaseBackend) -> str:
    if backend is DatabaseBackend.POSTGRES:
        return _POSTGRES_RESOURCE
    return _MSSQL_RESOURCE


def _fetch_access_token(scope: str) -> _CachedToken:
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise RuntimeError(
            "azure-identity is required when WF_USE_MANAGED_IDENTITY=1 "
            "(pip install methyl-gateway with azure-identity)"
        ) from exc

    client_id = os.environ.get("AZURE_CLIENT_ID", "").strip() or None
    credential = DefaultAzureCredential(
        managed_identity_client_id=client_id,
        exclude_interactive_browser_credential=True,
    )
    result = credential.get_token(scope)
    expires_on = float(getattr(result, "expires_on", time.time() + 3600))
    return _CachedToken(token=result.token, expires_on=expires_on)


def get_database_access_token(backend: DatabaseBackend) -> str:
    """Return a cached Azure AD access token for the given database backend."""
    scope = _token_scope(backend)
    now = time.time()
    with _lock:
        cached = _cache.get(scope)
        if cached is not None and cached.expires_on - now > _REFRESH_MARGIN_SECONDS:
            return cached.token
        fresh = _fetch_access_token(scope)
        _cache[scope] = fresh
        return fresh.token


def mssql_access_token_bytes(token: Optional[str] = None) -> bytes:
    """Packed access token for pyodbc SQL_COPT_SS_ACCESS_TOKEN (1256).

    msodbcsql expects a 4-byte little-endian length prefix followed by UTF-16-LE
    token bytes (ACCESSTOKEN struct). Passing raw UTF-16-LE without the prefix
    causes authentication failures or driver crashes.
    """
    value = token if token is not None else get_database_access_token(DatabaseBackend.MSSQL)
    encoded = value.encode("utf-16-le")
    return struct.pack("<I", len(encoded)) + encoded


def clear_token_cache() -> None:
    """Clear cached tokens (for tests)."""
    with _lock:
        _cache.clear()
