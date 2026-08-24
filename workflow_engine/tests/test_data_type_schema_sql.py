"""wf.data_type.schema_json is the SchemaPropertyGrid bind document."""

from __future__ import annotations

import unittest
from pathlib import Path

SQL_ROOT = Path(__file__).resolve().parents[1]
MSSQL = SQL_ROOT / "sql_mssql" / "wf_data_type.sql"
PG = SQL_ROOT / "sql_pg" / "wf_data_type.sql"


class DataTypeSchemaJsonSqlTests(unittest.TestCase):
    def test_both_backends_store_schema_json_on_data_type(self) -> None:
        for path in (MSSQL, PG):
            text = path.read_text(encoding="utf-8")
            self.assertRegex(text, r"schema_json", f"{path.name} must define schema_json")
            self.assertRegex(
                text,
                r"ADD COLUMN.*schema_json|schema_json json",
                f"{path.name} must add schema_json to wf.data_type",
            )
            self.assertIn("wf_repo_upsert_data_type", text)
            self.assertIn("p_schema_json" if path == PG else "@schema_json", text)

    def test_get_data_type_returns_schema_json(self) -> None:
        pg = PG.read_text(encoding="utf-8")
        mssql = MSSQL.read_text(encoding="utf-8")
        self.assertRegex(
            pg,
            r"wf_repo_get_data_type[\s\S]{0,2500}schema_json jsonb",
            "PG getter must project schema_json",
        )
        self.assertRegex(
            pg,
            r"portal\.sp_get_data_type[\s\S]{0,2500}schema_json jsonb",
            "PG portal getter must expose schema_json",
        )
        self.assertRegex(
            mssql,
            r"wf_repo_get_data_type[\s\S]{0,2500}t\.schema_json",
            "MSSQL getter must project schema_json",
        )

    def test_get_action_schema_prefers_type_schema_json(self) -> None:
        for path in (MSSQL, PG):
            text = path.read_text(encoding="utf-8")
            body = text.rsplit("wf_repo_get_action_schema", 1)[-1]
            self.assertIn("tin.schema_json", body)
            self.assertIn("tout.schema_json", body)
            self.assertRegex(body, r"COALESCE")

    def test_list_actions_has_schema_when_type_has_document(self) -> None:
        for path in (MSSQL, PG):
            text = path.read_text(encoding="utf-8")
            body = text.rsplit("wf_repo_list_actions", 1)[-1]
            self.assertIn("has_input_schema", body)
            self.assertIn("schema_json", body)

    def test_element_type_id_only_for_arrays(self) -> None:
        for path in (MSSQL, PG):
            text = path.read_text(encoding="utf-8")
            self.assertRegex(
                text,
                r"element_type_id IS NULL OR kind\s*=\s*'array'",
                f"{path.name} must constrain element_type_id to arrays",
            )

    def test_bind_action_types_casts_implementation_status(self) -> None:
        pg = PG.read_text(encoding="utf-8")
        self.assertRegex(
            pg,
            r"wf_repo_bind_action_types[\s\S]{0,2500}implementation_status::text",
            "PG bind must cast varchar implementation_status to text",
        )

    def test_seed_upserts_schema_json_parameter(self) -> None:
        seed = (
            SQL_ROOT / "sql_mssql" / "seed_data_types.py"
        ).read_text(encoding="utf-8")
        self.assertIn("@schema_json", seed)
        self.assertIn("%s::jsonb", seed)
        self.assertIn("editor_schema_document", seed)
        self.assertNotIn("Does not store schema documents", seed)
