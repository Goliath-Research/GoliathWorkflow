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

    def test_parallel_continue_drains_before_instance_fail(self) -> None:
        """One FAILED child must not fail the instance until all iterations finish."""
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
            fail_idx = re.search(
                r"parent_node_execution_id\s*=\s*(?:@foreach_execution_id|p_foreach_execution_id)"
                r".{0,200}status\s*=\s*N?'FAILED'",
                body[finished_idx.end() :],
                re.IGNORECASE | re.DOTALL,
            )
            self.assertIsNotNone(
                fail_idx,
                f"{path.name} must fail the instance only after all iterations are terminal",
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


if __name__ == "__main__":
    unittest.main()
