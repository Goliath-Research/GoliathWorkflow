"""Guard FOREACH continuation routing in the engine SQL scripts.

A FOREACH parent whose BODY is a composite (SEQUENCE/IF) is continued through
``wf_engine_continue_parent`` / ``wf_engine_on_action_complete``. When a base schema
script redefines those procedures without a FOREACH branch, the parent stays
``PENDING`` after its children reach ``SUCCEEDED`` and the instance never becomes
terminal. Every definition must therefore dispatch through the router proc.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import List, Tuple

SQL_ROOT = Path(__file__).resolve().parents[1]
MSSQL_DIR = SQL_ROOT / "sql_mssql"
PG_DIR = SQL_ROOT / "sql_pg"

ROUTER = "wf_foreach_route_continue"
CONTINUATION_PROCS = ("wf_engine_continue_parent", "wf_engine_on_action_complete")

_MSSQL_PROC = re.compile(
    r"CREATE\s+(?:OR\s+ALTER\s+)?PROCEDURE\s+wf\.(?P<name>\w+)(?P<body>.*?)(?=\bGO\b)",
    re.IGNORECASE | re.DOTALL,
)
_PG_PROC = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+wf\.(?P<name>\w+)(?P<body>.*?)\$\$;",
    re.IGNORECASE | re.DOTALL,
)


def _definitions(directory: Path, pattern: re.Pattern[str]) -> List[Tuple[Path, str, str]]:
    found: List[Tuple[Path, str, str]] = []
    for path in sorted(directory.rglob("*.sql")):
        if "deprecated" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            name = match.group("name").lower()
            if name in CONTINUATION_PROCS:
                found.append((path, name, match.group("body")))
    return found


class ForeachContinuationSqlTests(unittest.TestCase):
    def test_router_is_defined_for_both_backends(self) -> None:
        for directory, pattern in ((MSSQL_DIR, _MSSQL_PROC), (PG_DIR, _PG_PROC)):
            definitions = [
                path
                for path in sorted(directory.rglob("*.sql"))
                if re.search(
                    rf"CREATE\s+(?:OR\s+(?:ALTER|REPLACE)\s+)?PROCEDURE\s+wf\.{ROUTER}\b",
                    path.read_text(encoding="utf-8", errors="replace"),
                    re.IGNORECASE,
                )
            ]
            self.assertTrue(
                definitions, f"{directory.name} defines no wf.{ROUTER}"
            )

    def test_every_continuation_proc_routes_foreach(self) -> None:
        definitions = _definitions(MSSQL_DIR, _MSSQL_PROC) + _definitions(PG_DIR, _PG_PROC)
        self.assertTrue(definitions, "no continuation procedures found in SQL scripts")
        for path, name, body in definitions:
            with self.subTest(script=path.name, proc=name):
                self.assertIn(
                    "FOREACH",
                    body.upper(),
                    f"{path.name}:{name} has no FOREACH branch; a redeploy would strand "
                    "FOREACH parents in PENDING",
                )
                self.assertIn(
                    ROUTER,
                    body,
                    f"{path.name}:{name} must dispatch FOREACH through wf.{ROUTER}",
                )

    def test_router_is_sole_reader_of_foreach_parallel(self) -> None:
        """Only the router reads foreach_parallel for continuation decisions."""
        offenders: List[str] = []
        for path, name, body in _definitions(MSSQL_DIR, _MSSQL_PROC) + _definitions(
            PG_DIR, _PG_PROC
        ):
            if "foreach_parallel" in body.lower():
                offenders.append(f"{path.name}:{name}")
        self.assertEqual([], offenders)

    def test_parallel_continue_drains_then_completes(self) -> None:
        """One FAILED child must not fail the instance; after all iterations
        finish the FOREACH succeeds so missing/disqualified samples do not leave
        the instance RUNNING."""
        targets = (
            MSSQL_DIR / "wf_sql_foreach_support.sql",
            PG_DIR / "08_foreach_support.sql",
        )
        for path in targets:
            text = path.read_text(encoding="utf-8", errors="replace")
            match = re.search(
                r"CREATE\s+(?:OR\s+(?:ALTER|REPLACE)\s+)?PROCEDURE\s+"
                r"wf\.wf_foreach_parallel_continue(?P<body>.*?)(?:\bGO\b|\$\$;)",
                text,
                re.IGNORECASE | re.DOTALL,
            )
            self.assertIsNotNone(match, f"{path.name} missing wf_foreach_parallel_continue")
            body = match.group("body")
            finished_idx = re.search(
                r"(?:@finished|v_finished)\s*<\s*(?:@max|v_max)",
                body,
                re.IGNORECASE,
            )
            self.assertIsNotNone(
                finished_idx, f"{path.name} must wait until all FOREACH children finish"
            )
            after = body[finished_idx.end() :]
            self.assertIsNone(
                re.search(
                    r"workflow_instance\s+SET\s+status\s*=\s*N?'FAILED'",
                    after,
                    re.IGNORECASE,
                ),
                f"{path.name} must not fail the instance after FOREACH drain",
            )
            self.assertRegex(
                after,
                r"wf_engine_on_composite_complete",
                msg=f"{path.name} must close the FOREACH after all iterations are terminal",
            )
            early = body[: finished_idx.start()]
            self.assertIsNone(
                re.search(
                    r"parent_node_execution_id\s*=\s*(?:@foreach_execution_id|p_foreach_execution_id)"
                    r".{0,200}status\s*=\s*N?'FAILED'",
                    early,
                    re.IGNORECASE | re.DOTALL,
                ),
                f"{path.name} fail-fast on first FAILED child would strand sibling samples",
            )

    def test_action_fail_continues_parent(self) -> None:
        """Nested fail_task must continue the parent SEQUENCE/FOREACH or the graph freezes.

        A root-level ACTION (no parent) must fail the instance; leaving it RUNNING
        has no parent to drain.
        """
        targets = (
            (MSSQL_DIR / "wf_json_native_params.sql", "wf_engine_on_action_complete"),
            (MSSQL_DIR / "wf_sql_foreach_support.sql", "wf_engine_on_action_complete"),
            (MSSQL_DIR / "wf_sql_scope_writepath_parity.sql", "wf_engine_on_action_complete"),
            (PG_DIR / "03_engine_core.sql", "wf_engine_on_action_complete"),
            (PG_DIR / "06_scope_writepath_parity.sql", "wf_engine_on_action_complete"),
            (PG_DIR / "08_foreach_support.sql", "wf_engine_on_action_complete"),
        )
        for path, proc in targets:
            text = path.read_text(encoding="utf-8", errors="replace")
            pattern = _PG_PROC if path.parent.name == "sql_pg" else _MSSQL_PROC
            body = next(
                (m.group("body") for m in pattern.finditer(text) if m.group("name").lower() == proc),
                None,
            )
            self.assertIsNotNone(body, f"{path.name} missing {proc}")
            fail_m = re.search(
                r"(?:@result_code|p_result_code)\s*<\s*0(?P<fail>.*?)(?:UPDATE\s+wf\.node_execution\s+SET\s+status\s*=\s*N?'SUCCEEDED')",
                body,
                re.IGNORECASE | re.DOTALL,
            )
            self.assertIsNotNone(fail_m, f"{path.name}:{proc} missing result_code < 0 branch")
            fail = fail_m.group("fail")
            self.assertIn(
                "continue_parent",
                fail.lower(),
                f"{path.name}:{proc} fail path must call wf_engine_continue_parent",
            )
            parent_null = re.search(
                r"(?:@parent|v_parent)\s+IS\s+NULL",
                fail,
                re.IGNORECASE,
            )
            instance_failed = re.search(
                r"workflow_instance\s+SET\s+status\s*=\s*N?'FAILED'",
                fail,
                re.IGNORECASE,
            )
            self.assertIsNotNone(
                parent_null,
                f"{path.name}:{proc} fail path must handle a NULL parent",
            )
            self.assertIsNotNone(
                instance_failed,
                f"{path.name}:{proc} root ACTION fail must mark the instance FAILED",
            )
            self.assertLess(
                parent_null.start(),
                instance_failed.start(),
                f"{path.name}:{proc} instance FAILED must be gated on parent IS NULL",
            )

    def test_continue_parent_if_switch_propagates_branch_failure(self) -> None:
        """IF/SWITCH must not close as SUCCEEDED when the taken branch failed or was skipped.

        Otherwise the outer sample SEQUENCE treats the IF as success and activates
        leftover steps instead of skipping them.
        """
        targets = (
            MSSQL_DIR / "wf_sql_foreach_support.sql",
            PG_DIR / "03_engine_core.sql",
            PG_DIR / "08_foreach_support.sql",
        )
        for path in targets:
            text = path.read_text(encoding="utf-8", errors="replace")
            pattern = _PG_PROC if path.parent.name == "sql_pg" else _MSSQL_PROC
            body = next(
                (
                    m.group("body")
                    for m in pattern.finditer(text)
                    if m.group("name").lower() == "wf_engine_continue_parent"
                ),
                None,
            )
            self.assertIsNotNone(body, f"{path.name} missing wf_engine_continue_parent")
            if_arm = re.search(
                r"(?:@ptype|v_ptype)\s+IN\s*\(\s*N?'IF'.*?(?:ELSE IF|ELSIF|END IF|END;)",
                body,
                re.IGNORECASE | re.DOTALL,
            )
            self.assertIsNotNone(if_arm, f"{path.name} missing IF/SWITCH arm in continue_parent")
            arm = if_arm.group(0)
            self.assertRegex(
                arm,
                r"status\s+IN\s*\(\s*N?'FAILED'\s*,\s*N?'SKIPPED'\s*\)",
                msg=f"{path.name} IF/SWITCH must inspect FAILED/SKIPPED children",
            )
            self.assertRegex(
                arm,
                r"N?'FAILED'",
                msg=f"{path.name} IF/SWITCH must be able to close as FAILED",
            )

    def test_sequence_continue_skips_after_child_fail(self) -> None:
        """A FAILED sequence child must skip leftover steps, not fail the instance."""
        targets = (
            (MSSQL_DIR / "wf_sql_foreach_support.sql", _MSSQL_PROC),
            (PG_DIR / "03_engine_core.sql", _PG_PROC),
        )
        for path, pattern in targets:
            text = path.read_text(encoding="utf-8", errors="replace")
            body = next(
                (
                    m.group("body")
                    for m in pattern.finditer(text)
                    if m.group("name").lower() == "wf_sequence_continue"
                ),
                None,
            )
            self.assertIsNotNone(body, f"{path.name} missing wf_sequence_continue")
            self.assertIn("SKIPPED", body.upper(), f"{path.name} must skip leftover sequence steps")
            self.assertIsNone(
                re.search(
                    r"workflow_instance\s+SET\s+status\s*=\s*N?'FAILED'",
                    body,
                    re.IGNORECASE,
                ),
                f"{path.name} sequence_continue must not fail the instance on a child fail",
            )

    def test_archive_dest_missing_resolves_as_null(self) -> None:
        scripts = (
            MSSQL_DIR / "wf_sql_foreach_support.sql",
            MSSQL_DIR / "wf_sql_runtime_parity.sql",
            PG_DIR / "05_runtime_parity.sql",
        )
        for path in scripts:
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertIn(
                "sampleDestination",
                text,
                f"{path.name} must treat missing sampleDestination as JSON null",
            )
            self.assertIn("h5Destination", text, path.name)
            self.assertIn(
                "rejectReason",
                text,
                f"{path.name} must treat missing rejectReason as JSON null",
            )


if __name__ == "__main__":
    unittest.main()
