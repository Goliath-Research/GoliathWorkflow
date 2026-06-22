"""Resolve workflow gateway database connection settings from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DatabaseBackend(str, Enum):
    MSSQL = "mssql"
    POSTGRES = "postgres"


@dataclass(frozen=True)
class GatewayConnectionConfig:
    backend: DatabaseBackend
    schema_name: str
    connection_string: str
    use_managed_identity: bool = False

    @property
    def schema_dot(self) -> str:
        return f"{self.schema_name}."


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_flag(name: str) -> bool:
    value = _env(name).lower()
    return value in ("1", "true", "yes")


def get_database_backend() -> DatabaseBackend:
    value = _env("BACKEND_DB", "mssql").lower()
    if value in ("postgres", "postgresql", "pg"):
        return DatabaseBackend.POSTGRES
    return DatabaseBackend.MSSQL


def resolve_schema_name() -> str:
    schema = _env("WF_SCHEMA")
    return schema or "wf"


def build_postgres_conninfo(*, use_managed_identity: bool = False) -> str:
    override = _env("METHYLPIPELINE_DB")
    if override:
        return override

    host = _env("POSTGRES_HOST", "localhost")
    port = _env("POSTGRES_PORT", "5432")
    db = _env("POSTGRES_DB", "methylpipeline")
    user = _env("POSTGRES_USER", "postgres")
    if use_managed_identity:
        # Password is supplied at connect time via Entra token.
        return f"postgresql://{user}@{host}:{port}/{db}?sslmode=require"
    password = _env("POSTGRES_PASSWORD")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def build_mssql_conninfo(*, use_managed_identity: bool = False) -> str:
    override = _env("METHYLPIPELINE_DB")
    if override:
        return override

    server = _env("AZURE_SQL_SERVER")
    database = _env("AZURE_SQL_DB")
    user = _env("AZURE_SQL_USER")
    password = _env("AZURE_SQL_PASSWORD")

    if server and database:
        parts = [
            f"DRIVER={{ODBC Driver 18 for SQL Server}}",
            f"SERVER={server},1433",
            f"DATABASE={database}",
            "Encrypt=yes",
            "TrustServerCertificate=no",
        ]
        if not use_managed_identity:
            if user:
                parts.append(f"UID={user}")
            if password:
                parts.append(f"PWD={password}")
        return ";".join(parts)

    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=localhost;DATABASE=MethylPipeline;"
        "Trusted_Connection=yes;Encrypt=yes"
    )


def resolve_connection_config(
    *,
    backend: Optional[DatabaseBackend] = None,
    connection_string: Optional[str] = None,
) -> GatewayConnectionConfig:
    resolved_backend = backend or get_database_backend()
    use_mi = _env_flag("WF_USE_MANAGED_IDENTITY")
    conn = connection_string or _env("METHYLPIPELINE_DB")
    if not conn:
        conn = (
            build_postgres_conninfo(use_managed_identity=use_mi)
            if resolved_backend is DatabaseBackend.POSTGRES
            else build_mssql_conninfo(use_managed_identity=use_mi)
        )
    return GatewayConnectionConfig(
        backend=resolved_backend,
        schema_name=resolve_schema_name(),
        connection_string=conn,
        use_managed_identity=use_mi,
    )
