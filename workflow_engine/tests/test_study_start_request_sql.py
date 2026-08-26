"""Study start queue SQL must exist as twins; Portal queues, Python bakes."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SQL_ROOT = Path(__file__).resolve().parents[1]
MSSQL = SQL_ROOT / "sql_mssql" / "cfg_study_start_request.sql"
PG = SQL_ROOT / "sql_pg" / "cfg_study_start_request.sql"

PROCS = (
    "sp_preview_study_start",
    "sp_request_study_start",
    "sp_claim_study_start_request",
    "sp_complete_study_start_request",
    "sp_fail_study_start_request",
    "sp_get_study_start_request",
    "sp_list_study_start_stages",
)


class StudyStartRequestSqlTests(unittest.TestCase):
    def test_twins_define_table_and_queue_procs(self) -> None:
        for path in (MSSQL, PG):
            text = path.read_text(encoding="utf-8")
            self.assertIn("cfg.study_start_request", text)
            self.assertIn("sample_prep", text)
            self.assertIn("study_validation", text)
            self.assertIn("lease_expires_at_utc", text)
            for name in PROCS:
                self.assertIn(name, text, f"{path.name} missing {name}")

    def test_preview_does_not_bake_resolved_config(self) -> None:
        for path in (MSSQL, PG):
            body = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                body,
                r"resolve_action_config|resolvedConfig__",
                f"{path.name} must not bake resolvedConfig",
            )

    def test_claim_uses_a_lease(self) -> None:
        mssql = re.search(
            r"sp_claim_study_start_request(?P<body>.*?)(?=\bGO\b)",
            MSSQL.read_text(encoding="utf-8"),
            re.IGNORECASE | re.DOTALL,
        )
        pg = re.search(
            r"sp_claim_study_start_request(?P<body>.*?)\$\$;",
            PG.read_text(encoding="utf-8"),
            re.IGNORECASE | re.DOTALL,
        )
        self.assertIsNotNone(mssql)
        self.assertIsNotNone(pg)
        self.assertIn("UPDLOCK", mssql.group("body"))
        self.assertIn("SKIP LOCKED", pg.group("body"))
