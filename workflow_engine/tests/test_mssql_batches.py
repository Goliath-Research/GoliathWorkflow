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

from rest.db.mssql import (  # noqa: E402
    MssqlGatewayDb,
    _JSON_CAST,
    _MSSQL_OUTPUT_BATCH_PREFIX,
)


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


class MssqlJsonBindingTests(unittest.TestCase):
    def test_json_params_use_cast_not_raw_placeholder(self) -> None:
        db = MssqlGatewayDb("DRIVER={ODBC Driver 18 for SQL Server};SERVER=x", schema_name="wf")
        captured: list[str] = []

        def fake_fetch_one(_self, sql: str, params=()):
            captured.append(sql)
            if "wf_repo_create_workflow_graph" in sql:
                return {
                    "workflow_def_id": 1,
                    "workflow_version_id": 2,
                    "root_node_id": 3,
                    "name": "TestFlow",
                }
            if "wf_repo_create_workflow_instance" in sql:
                return {"id": 99}
            return {"accepted": True, "instance_status": "RUNNING", "next_ready_count": 0}

        def fake_exec_proc(_self, sql: str, params=()):
            captured.append(sql)

        with mock.patch.object(MssqlGatewayDb, "_fetch_one", fake_fetch_one):
            with mock.patch.object(MssqlGatewayDb, "_exec_proc", fake_exec_proc):
                db.create_workflow_definition({"name": "TestFlow", "root_node_key": "root", "nodes": []})
                db.create_workflow_instance(2, {"projectPath": "/p"})
                db.worker_submit_result(1, 2, "tok", 0, {"ok": True})
                db.apply_validation_plan(1, {"iterations": []})
                db.upsert_action_schema("pipeline.centroid", "input", {"type": "object"}, "pipeline.centroid")

        json_sql = [sql for sql in captured if "@__json_" in sql]
        self.assertGreaterEqual(len(json_sql), 5)
        for sql in json_sql:
            self.assertIn("DECLARE @__json_", sql)
            self.assertNotRegex(sql, r"@(?:spec|context_json|schema_json|output_json)=\?(?!\s*[,)])")


if __name__ == "__main__":
    unittest.main()
