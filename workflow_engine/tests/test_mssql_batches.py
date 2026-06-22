"""Tests for MSSQL gateway SQL batch construction."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

# MssqlGatewayDb imports pyodbc at module load; stub when ODBC is unavailable.
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = types.ModuleType("pyodbc")
    sys.modules["pyodbc"].Error = Exception

REST_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REST_DIR))

from rest.db.mssql import MssqlGatewayDb, _MSSQL_OUTPUT_BATCH_PREFIX  # noqa: E402


class MssqlOutputBatchTests(unittest.TestCase):
    def test_output_batches_include_set_nocount(self) -> None:
        db = MssqlGatewayDb("DRIVER={ODBC Driver 18 for SQL Server};SERVER=x", schema_name="wf")
        self.assertEqual(_MSSQL_OUTPUT_BATCH_PREFIX, "SET NOCOUNT ON;\n")

        captured: list[str] = []

        def fake_fetch_one(_self, sql: str, params=()):
            captured.append(sql)
            if "deleted_instance_count" in sql:
                return {"deleted_instance_count": 1, "deleted_version_count": 1}
            return {"accepted": True, "instance_status": "RUNNING", "next_ready_count": 0}

        with mock.patch.object(MssqlGatewayDb, "_fetch_one", fake_fetch_one):
            db.worker_submit_result(1, 2, "tok", 0, {"ok": True})
            db.delete_workflow_definition("DemoFlow", True)

        self.assertEqual(len(captured), 2)
        for sql in captured:
            self.assertTrue(
                sql.startswith("SET NOCOUNT ON;"),
                f"expected SET NOCOUNT ON prefix, got: {sql[:80]!r}",
            )
            self.assertIn("SELECT @", sql)


if __name__ == "__main__":
    unittest.main()
