#!/usr/bin/env python3
"""
Seed wf.workflow_action rows and schemas from the unified action catalog.

Requires PostgreSQL wf schema with wf_repo_upsert_workflow_action and wf_action_schema deployed.

Usage:
  python workflow_engine/sql/seed_action_catalog.py
  python workflow_engine/sql/seed_action_catalog.py --dsn postgresql://...
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "schemas" / "actions" / "catalog.json"
TASKS_DIR = REPO_ROOT / "schemas" / "tasks"

sys.path.insert(0, str(REPO_ROOT / "workers"))

from methyl_worker.action_catalog_export import export_action_catalog  # noqa: E402
from methyl_worker.task_schema_registry import list_task_schema_specs  # noqa: E402


def pg_dsn() -> str:
    import os

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "methylpipeline_parity")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "methyl")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _json_literal(obj: dict) -> str:
    escaped = json.dumps(obj, separators=(",", ":")).replace("'", "''")
    return f"'{escaped}'::jsonb"


def exec_sql(dsn: str, sql: str) -> None:
    subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
    )


def upsert_action(dsn: str, action_name: str, capability: str, payload_schema_ref: str | None) -> None:
    cap = _sql_literal(capability) if capability else "NULL"
    ref = _sql_literal(payload_schema_ref) if payload_schema_ref else "NULL"
    exec_sql(
        dsn,
        f"CALL wf.wf_repo_upsert_workflow_action({_sql_literal(action_name)}, {cap}, {ref});",
    )


def upsert_schema(dsn: str, action_name: str, direction: str, schema: dict, schema_id: str) -> None:
    exec_sql(
        dsn,
        "CALL wf.wf_repo_upsert_action_schema("
        f"{_sql_literal(action_name)}, "
        f"{_sql_literal(direction)}, "
        f"{_json_literal(schema)}, "
        f"{_sql_literal(schema_id)});",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed wf.workflow_action + schemas from schemas/actions/catalog.json"
    )
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN (default: POSTGRES_* env)")
    parser.add_argument(
        "--regenerate-catalog",
        action="store_true",
        help="Run methyl-export-action-catalog before seeding",
    )
    args = parser.parse_args(argv)
    dsn = args.dsn or pg_dsn()

    if args.regenerate_catalog:
        export_action_catalog(write=True)

    if not CATALOG_PATH.is_file():
        print(f"Missing {CATALOG_PATH}; run methyl-export-action-catalog first.", file=sys.stderr)
        return 1

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    actions = catalog.get("actions") or []

    action_count = 0
    for action in actions:
        upsert_action(
            dsn,
            str(action["action_name"]),
            str(action.get("capability") or ""),
            str(action.get("schema_id") or action["action_name"]),
        )
        action_count += 1
        print(f"Upserted action {action['action_name']}")

    schema_count = 0
    if not TASKS_DIR.is_dir():
        print(f"Missing {TASKS_DIR}; run methyl-export-task-schemas first.", file=sys.stderr)
        return 1

    for spec in list_task_schema_specs():
        for direction, filename in (
            ("input", spec.input_filename),
            ("output", spec.output_filename),
        ):
            path = TASKS_DIR / filename
            if not path.is_file():
                print(f"Skip missing {path}", file=sys.stderr)
                continue
            schema = json.loads(path.read_text(encoding="utf-8"))
            upsert_schema(dsn, spec.action_name, direction, schema, spec.schema_id)
            schema_count += 1
            print(f"Upserted schema {spec.action_name} ({direction})")

    print(f"Seeded {action_count} action(s) and {schema_count} schema(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
