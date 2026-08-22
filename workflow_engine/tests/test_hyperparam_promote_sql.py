"""Guard HPO promote against wholesale actionConfig replace.

Trial ``overrides_json`` stores dotted paths (``validation.stability_dmp_freq``).
``sp_set_study_action_config_overlay`` replaces ``document_json.actionConfig``.
Promote must expand those paths onto the existing nested overlay first.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SQL_ROOT = Path(__file__).resolve().parents[1]
MSSQL = SQL_ROOT / "sql_mssql" / "cfg_hyperparameter_search.sql"
PG = SQL_ROOT / "sql_pg" / "cfg_hyperparameter_search.sql"

_HELPER = "fn_apply_dotted_action_config"
_PROMOTE = "sp_promote_hyperparam_winner"


def _mssql_proc(text: str, name: str) -> str:
    match = re.search(
        rf"CREATE\s+OR\s+ALTER\s+PROCEDURE\s+portal\.{name}(?P<body>.*?)(?=\bGO\b)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing portal.{name} in MSSQL"
    return match.group("body")


def _pg_func(text: str, name: str) -> str:
    match = re.search(
        rf"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+portal\.{name}(?P<body>.*?)\$\$;",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing portal.{name} in PG"
    return match.group("body")


class HyperparamPromoteSqlTests(unittest.TestCase):
    def test_both_backends_define_dotted_merge_helper(self) -> None:
        for path in (MSSQL, PG):
            text = path.read_text(encoding="utf-8")
            self.assertRegex(
                text,
                rf"CREATE\s+OR\s+(?:ALTER|REPLACE)\s+(?:FUNCTION|PROCEDURE)\s+portal\.{_HELPER}",
                f"{path.name} must define portal.{_HELPER}",
            )

    def test_promote_merges_existing_action_config_then_sets_overlay(self) -> None:
        mssql = _mssql_proc(MSSQL.read_text(encoding="utf-8"), _PROMOTE)
        pg = _pg_func(PG.read_text(encoding="utf-8"), _PROMOTE)
        for label, body in (("mssql", mssql), ("pg", pg)):
            with self.subTest(backend=label):
                self.assertIn(_HELPER, body, f"{label} promote must apply dotted overrides")
                self.assertIn(
                    "actionConfig",
                    body,
                    f"{label} promote must read the existing study actionConfig",
                )
                self.assertIn(
                    "sp_set_study_action_config_overlay",
                    body,
                    f"{label} promote still writes through the study overlay setter",
                )
                self.assertNotRegex(
                    body,
                    r"sp_set_study_action_config_overlay\s*\(\s*(?:v_study,\s*v_overrides|@study_row_id\s*=\s*@study_row_id,\s*@action_config_overlay\s*=\s*@overrides)",
                    f"{label} must not pass raw trial overrides_json to the setter",
                )

    def test_helper_deletes_on_json_null(self) -> None:
        for path in (MSSQL, PG):
            text = path.read_text(encoding="utf-8")
            self.assertTrue(
                "JSON_MODIFY(@cur, @path, NULL)" in text or "#- segs" in text,
                f"{path.name} helper must delete a leaf when the override is JSON null",
            )


if __name__ == "__main__":
    unittest.main()
