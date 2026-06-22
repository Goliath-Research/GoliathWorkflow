"""Tests for workflow gateway connection configuration."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REST_DIR = Path(__file__).resolve().parents[1] / "rest"
sys.path.insert(0, str(REST_DIR))

from connection import (  # noqa: E402
    DatabaseBackend,
    build_mssql_conninfo,
    build_postgres_conninfo,
    get_database_backend,
    resolve_connection_config,
    resolve_schema_name,
)


class ConnectionConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved)

    def test_default_backend_is_mssql(self) -> None:
        os.environ.pop("BACKEND_DB", None)
        self.assertEqual(get_database_backend(), DatabaseBackend.MSSQL)

    def test_postgres_backend_aliases(self) -> None:
        for value in ("postgres", "postgresql", "pg"):
            os.environ["BACKEND_DB"] = value
            self.assertEqual(get_database_backend(), DatabaseBackend.POSTGRES)

    def test_schema_default(self) -> None:
        os.environ.pop("WF_SCHEMA", None)
        self.assertEqual(resolve_schema_name(), "wf")

    def test_postgres_conninfo_from_env(self) -> None:
        os.environ.pop("METHYLPIPELINE_DB", None)
        os.environ.update(
            {
                "POSTGRES_HOST": "db.example.com",
                "POSTGRES_PORT": "5433",
                "POSTGRES_DB": "methyl",
                "POSTGRES_USER": "dba",
                "POSTGRES_PASSWORD": "secret",
            }
        )
        self.assertEqual(
            build_postgres_conninfo(),
            "postgresql://dba:secret@db.example.com:5433/methyl",
        )

    def test_mssql_conninfo_from_azure_env(self) -> None:
        os.environ.pop("METHYLPIPELINE_DB", None)
        os.environ.update(
            {
                "AZURE_SQL_SERVER": "myserver.database.windows.net",
                "AZURE_SQL_DB": "MethylPipeline",
                "AZURE_SQL_USER": "sqladmin",
                "AZURE_SQL_PASSWORD": "pass",
            }
        )
        conn = build_mssql_conninfo()
        self.assertIn("myserver.database.windows.net", conn)
        self.assertIn("DATABASE=MethylPipeline", conn)
        self.assertIn("UID=sqladmin", conn)
        self.assertIn("PWD=pass", conn)

    def test_methylpipeline_db_override(self) -> None:
        os.environ["METHYLPIPELINE_DB"] = "postgresql://u:p@host/db"
        os.environ["BACKEND_DB"] = "mssql"
        cfg = resolve_connection_config()
        self.assertEqual(cfg.connection_string, "postgresql://u:p@host/db")
        self.assertEqual(cfg.backend, DatabaseBackend.MSSQL)

    def test_managed_identity_flag(self) -> None:
        os.environ["WF_USE_MANAGED_IDENTITY"] = "1"
        cfg = resolve_connection_config(backend=DatabaseBackend.POSTGRES)
        self.assertTrue(cfg.use_managed_identity)

    def test_mssql_conninfo_omits_credentials_when_mi(self) -> None:
        os.environ.pop("METHYLPIPELINE_DB", None)
        os.environ.update(
            {
                "AZURE_SQL_SERVER": "myserver.database.windows.net",
                "AZURE_SQL_DB": "MethylPipeline",
                "AZURE_SQL_USER": "sqladmin",
                "AZURE_SQL_PASSWORD": "pass",
            }
        )
        conn = build_mssql_conninfo(use_managed_identity=True)
        self.assertIn("DATABASE=MethylPipeline", conn)
        self.assertNotIn("UID=", conn)
        self.assertNotIn("PWD=", conn)

    def test_postgres_conninfo_sslmode_when_mi(self) -> None:
        os.environ.pop("METHYLPIPELINE_DB", None)
        os.environ.update(
            {
                "POSTGRES_HOST": "pg.example.com",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "methyl",
                "POSTGRES_USER": "mi-principal",
                "POSTGRES_PASSWORD": "ignored",
            }
        )
        conn = build_postgres_conninfo(use_managed_identity=True)
        self.assertEqual(
            conn,
            "postgresql://mi-principal@pg.example.com:5432/methyl?sslmode=require",
        )
        self.assertNotIn("ignored", conn)

    def test_resolve_config_builds_mi_mssql_string(self) -> None:
        os.environ.pop("METHYLPIPELINE_DB", None)
        os.environ.update(
            {
                "BACKEND_DB": "mssql",
                "WF_USE_MANAGED_IDENTITY": "1",
                "AZURE_SQL_SERVER": "srv.database.windows.net",
                "AZURE_SQL_DB": "MethylPipeline",
                "AZURE_SQL_USER": "should-not-appear",
                "AZURE_SQL_PASSWORD": "secret",
            }
        )
        cfg = resolve_connection_config()
        self.assertTrue(cfg.use_managed_identity)
        self.assertNotIn("UID=", cfg.connection_string)
        self.assertNotIn("PWD=", cfg.connection_string)


if __name__ == "__main__":
    unittest.main()
