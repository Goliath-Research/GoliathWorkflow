"""Gateway database backend factory."""

from __future__ import annotations

from typing import Optional

from ..connection import DatabaseBackend, GatewayConnectionConfig, resolve_connection_config
from .base import GatewayDb


def open_gateway_db(config: Optional[GatewayConnectionConfig] = None) -> GatewayDb:
    if config is None:
        config = resolve_connection_config()

    if config.use_managed_identity:
        raise NotImplementedError(
            "WF_USE_MANAGED_IDENTITY is not implemented yet; use SQL user/password for phase 1."
        )

    if config.backend is DatabaseBackend.POSTGRES:
        from .postgres import PostgresGatewayDb

        return PostgresGatewayDb(config.connection_string, schema_name=config.schema_name)

    from .mssql import MssqlGatewayDb

    return MssqlGatewayDb(config.connection_string, schema_name=config.schema_name)
