"""Layered site/profile/procedure guardrail editor SQL twins."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SQL_ROOT = Path(__file__).resolve().parents[1]
MSSQL = SQL_ROOT / "sql_mssql" / "portal_guardrails_editor.sql"
PG = SQL_ROOT / "sql_pg" / "portal_guardrails_editor.sql"
MSSQL_CATALOG = SQL_ROOT / "sql_mssql" / "cfg_process_pack_catalog.sql"
PG_CATALOG = SQL_ROOT / "sql_pg" / "cfg_process_pack_catalog.sql"


def _pg_func(text: str, name: str) -> str:
    match = re.search(
        rf"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+portal\.{name}(?P<body>.*?)\$\$;",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing portal.{name} in PG"
    return match.group("body")


def _mssql_routine(text: str, name: str) -> str:
    match = re.search(
        rf"CREATE\s+OR\s+ALTER\s+(?:FUNCTION|PROCEDURE)\s+portal\.{name}(?P<body>.*?)(?=\bGO\b)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing portal.{name} in MSSQL"
    return match.group("body")


class LayeredGuardrailsEditorSqlTests(unittest.TestCase):
    def test_both_backends_define_editors_and_full_window(self) -> None:
        for path in (MSSQL, PG):
            text = path.read_text(encoding="utf-8")
            for name in (
                "sp_get_site_guardrails_editor",
                "sp_set_site_guardrails_editor",
                "sp_get_profile_guardrails_editor",
                "sp_set_profile_guardrails_editor",
                "sp_get_assay_procedure_guardrails_editor",
                "sp_set_assay_procedure_guardrails_editor",
            ):
                self.assertIn(name, text, f"{path.name} missing {name}")
            self.assertIn("sample_prep_guardrails", text)
            self.assertIn("sample_prep_guardrails_overlay", text)
            self.assertRegex(text, r"fn_json(?:b)?_full_window_ok")
            self.assertRegex(text, r"fn_(?:json_)?guardrail_draft_version")

    def test_site_setter_requires_full_window_not_sparse_diff(self) -> None:
        pg = _pg_func(PG.read_text(encoding="utf-8"), "sp_set_site_guardrails_editor")
        mssql = _mssql_routine(
            MSSQL.read_text(encoding="utf-8"), "sp_set_site_guardrails_editor"
        )
        for label, body in (("pg", pg), ("mssql", mssql)):
            with self.subTest(backend=label):
                self.assertRegex(body, r"fn_json(?:b)?_full_window_ok")
                self.assertNotRegex(body, r"fn_json(?:b)?_sparse_diff")
                self.assertIn("edited_effective", body)

    def test_profile_and_procedure_setters_use_sparse_diff(self) -> None:
        pg_text = PG.read_text(encoding="utf-8")
        mssql_text = MSSQL.read_text(encoding="utf-8")
        for name in (
            "sp_set_profile_guardrails_editor",
            "sp_set_assay_procedure_guardrails_editor",
        ):
            pg = _pg_func(pg_text, name)
            mssql = _mssql_routine(mssql_text, name)
            for label, body in (("pg", pg), ("mssql", mssql)):
                with self.subTest(backend=label, proc=name):
                    self.assertRegex(body, r"fn_json(?:b)?_sparse_diff")
                self.assertIn("cfg_repo_upsert", body)
                self.assertNotRegex(body, r"UPDATE\s+cfg\.(pipeline_profile|assay_procedure)")

    def test_catalog_defines_upsert_and_publish(self) -> None:
        for path in (MSSQL_CATALOG, PG_CATALOG):
            text = path.read_text(encoding="utf-8")
            for name in (
                "sp_upsert_pipeline_profile",
                "sp_publish_pipeline_profile",
                "sp_upsert_assay_procedure",
                "sp_publish_assay_procedure",
            ):
                self.assertIn(name, text, f"{path.name} missing {name}")
