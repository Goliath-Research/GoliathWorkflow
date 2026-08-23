"""Guardrails editor SQL must compose inherited values and persist a sparse diff."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SQL_ROOT = Path(__file__).resolve().parents[1]
MSSQL = SQL_ROOT / "sql_mssql" / "portal_study_ops_api.sql"
PG = SQL_ROOT / "sql_pg" / "portal_study_ops_api.sql"


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


class StudyGuardrailsEditorSqlTests(unittest.TestCase):
    def test_both_backends_define_compose_and_diff_helpers(self) -> None:
        for path in (MSSQL, PG):
            text = path.read_text(encoding="utf-8")
            self.assertRegex(
                text,
                r"fn_json(?:b)?_deep_merge",
                f"{path.name} must define deep_merge",
            )
            self.assertRegex(
                text,
                r"fn_json(?:b)?_sparse_diff",
                f"{path.name} must define sparse_diff",
            )
            self.assertRegex(
                text,
                r"fn_json(?:b)?_guardrail_slice",
                f"{path.name} must slice alignment_qc/extraction_qc",
            )
            self.assertIn("sp_get_study_guardrails_editor", text)
            self.assertIn("sp_set_study_guardrails_editor", text)
            self.assertIn("study_action_config_overlay", text)

    def test_getter_returns_effective_not_overlay_only(self) -> None:
        pg = _pg_func(PG.read_text(encoding="utf-8"), "sp_get_study_guardrails_editor")
        mssql = _mssql_routine(
            MSSQL.read_text(encoding="utf-8"), "sp_get_study_guardrails_editor"
        )
        for label, body in (("pg", pg), ("mssql", mssql)):
            with self.subTest(backend=label):
                self.assertIn("inherited_guardrails", body)
                self.assertIn("effective_guardrails", body)
                self.assertIn("schema_id", body)
                self.assertRegex(body, r"pipeline_profile|pipelineProfile")

    def test_setter_diffs_against_inherited_and_keeps_other_keys(self) -> None:
        pg = _pg_func(PG.read_text(encoding="utf-8"), "sp_set_study_guardrails_editor")
        mssql = _mssql_routine(
            MSSQL.read_text(encoding="utf-8"), "sp_set_study_guardrails_editor"
        )
        for label, body in (("pg", pg), ("mssql", mssql)):
            with self.subTest(backend=label):
                self.assertRegex(body, r"fn_json(?:b)?_sparse_diff")
                self.assertRegex(body, r"fn_json(?:b)?_guardrail_slice")
                self.assertIn("alignment_qc", body)
                self.assertIn("extraction_qc", body)
                self.assertIn("edited_effective", body)
                self.assertNotIn("sp_set_study_action_config_overlay", body)

    def test_slice_strips_workflow_identity(self) -> None:
        for path in (MSSQL, PG):
            text = path.read_text(encoding="utf-8")
            self.assertIn("sample_paths", text)
            self.assertIn("output_dir", text)
            self.assertIn("genome_fasta", text)
