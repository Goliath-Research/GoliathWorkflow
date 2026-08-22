"""Guard engine continue/activate against a cancelled or failed instance.

``portal.sp_cancel_instance`` / ``sp_fail_instance`` drain READY/PENDING and mark
the instance terminal. An in-flight ACTION that later succeeds still used to
call ``wf_sequence_continue`` / ``wf_foreach_continue``, which inserted new
READY children (align after a cancelled SamplePrep download). Last-wins copies
must refuse that work when ``workflow_instance.status`` is not RUNNING.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import List, Tuple

SQL_ROOT = Path(__file__).resolve().parents[1]
MSSQL_DIR = SQL_ROOT / "sql_mssql"
PG_DIR = SQL_ROOT / "sql_pg"

# Last-wins / incrementally deployed copies that operators actually apply.
LAST_WINS: Tuple[Tuple[Path, Tuple[str, ...]], ...] = (
    (
        MSSQL_DIR / "wf_action_dispatch_affinity.sql",
        ("wf_engine_activate",),
    ),
    (
        MSSQL_DIR / "wf_json_native_params.sql",
        ("wf_engine_on_action_complete",),
    ),
    (
        MSSQL_DIR / "wf_sql_foreach_support.sql",
        (
            "wf_engine_activate",
            "wf_engine_on_action_complete",
            "wf_sequence_continue",
            "wf_foreach_continue",
            "wf_foreach_parallel_continue",
            "wf_engine_continue_parent",
        ),
    ),
    (
        PG_DIR / "03_engine_core.sql",
        ("wf_sequence_continue", "wf_engine_activate", "wf_engine_on_action_complete"),
    ),
    (
        PG_DIR / "08_foreach_support.sql",
        (
            "wf_engine_activate",
            "wf_engine_on_action_complete",
            "wf_foreach_continue",
            "wf_foreach_parallel_continue",
            "wf_engine_continue_parent",
        ),
    ),
)

_MSSQL_PROC = re.compile(
    r"CREATE\s+(?:OR\s+ALTER\s+)?PROCEDURE\s+wf\.(?P<name>\w+)(?P<body>.*?)(?=\bGO\b)",
    re.IGNORECASE | re.DOTALL,
)
_PG_PROC = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+wf\.(?P<name>\w+)(?P<body>.*?)\$\$;",
    re.IGNORECASE | re.DOTALL,
)

_RUNNING_GUARD = re.compile(
    r"status\s*=\s*N?'RUNNING'",
    re.IGNORECASE,
)


def _bodies(path: Path) -> List[Tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    pattern = _PG_PROC if path.parent.name == "sql_pg" else _MSSQL_PROC
    return [(m.group("name").lower(), m.group("body")) for m in pattern.finditer(text)]


class InstanceTerminalGuardSqlTests(unittest.TestCase):
    def test_last_wins_refuse_work_when_instance_not_running(self) -> None:
        for path, names in LAST_WINS:
            bodies = {name: body for name, body in _bodies(path)}
            for name in names:
                with self.subTest(script=path.name, proc=name):
                    self.assertIn(name, bodies, f"{path.name} missing wf.{name}")
                    self.assertRegex(
                        bodies[name],
                        _RUNNING_GUARD,
                        f"{path.name}:{name} must refuse work unless "
                        "workflow_instance.status is RUNNING",
                    )

    def test_foreach_continue_checks_before_loop_state_bump(self) -> None:
        """Sequential FOREACH must not increment loop_state after cancel."""
        targets = (
            MSSQL_DIR / "wf_sql_foreach_support.sql",
            PG_DIR / "08_foreach_support.sql",
        )
        for path in targets:
            bodies = {name: body for name, body in _bodies(path)}
            body = bodies["wf_foreach_continue"]
            guard = _RUNNING_GUARD.search(body)
            bump = re.search(
                r"(?:SET\s+@cur\s*\+=\s*1|v_cur\s*:=\s*v_cur\s*\+\s*1)",
                body,
                re.IGNORECASE,
            )
            self.assertIsNotNone(guard, f"{path.name} foreach_continue missing RUNNING guard")
            self.assertIsNotNone(bump, f"{path.name} foreach_continue missing loop increment")
            self.assertLess(
                guard.start(),
                bump.start(),
                f"{path.name} must check instance status before incrementing loop_state",
            )


if __name__ == "__main__":
    unittest.main()
