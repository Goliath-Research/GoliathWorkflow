#!/usr/bin/env python3
"""
Seed wf.workflow_action rows and schemas from the unified action catalog.

Uses the gateway DB layer (Azure SQL or PostgreSQL) via BACKEND_DB / connection env.
Legacy PostgreSQL-only path: pass --dsn postgresql://...

Usage:
  source .venv/bin/activate
  methyl-export-task-schemas
  methyl-export-action-catalog
  python workflow_engine/sql_mssql/seed_action_catalog.py

Azure SQL (default BACKEND_DB=mssql):
  export BACKEND_DB=mssql
  export AZURE_SQL_SERVER=...
  export AZURE_SQL_DB=...
  export AZURE_SQL_USER=...
  export AZURE_SQL_PASSWORD=...
  python workflow_engine/sql_mssql/seed_action_catalog.py
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
WF_ENGINE = REPO_ROOT / "workflow_engine"

sys.path.insert(0, str(REPO_ROOT / "workers"))
sys.path.insert(0, str(WF_ENGINE))

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


def _exec_psql(dsn: str, sql: str) -> None:
    subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
    )


def _upsert_action_psql(
    dsn: str,
    action_name: str,
    capability: str,
    payload_schema_ref: str | None,
    *,
    execution_mode: str | None = None,
    cli_tool: str | None = None,
    in_process_handler: str | None = None,
    argv_map: dict | None = None,
) -> None:
    """Upsert via 7-arg ``wf_repo_upsert_workflow_action`` (dispatch metadata)."""
    cap = _sql_literal(capability) if capability else "NULL"
    ref = _sql_literal(payload_schema_ref) if payload_schema_ref else "NULL"
    mode = _sql_literal(execution_mode) if execution_mode else "NULL"
    tool = _sql_literal(cli_tool) if cli_tool else "NULL"
    handler = _sql_literal(in_process_handler) if in_process_handler else "NULL"
    argv = _json_literal(argv_map) if isinstance(argv_map, dict) else "NULL"
    _exec_psql(
        dsn,
        "CALL wf.wf_repo_upsert_workflow_action("
        f"{_sql_literal(action_name)}, {cap}, {ref}, {mode}, {tool}, {handler}, {argv});",
    )


def _upsert_schema_psql(
    dsn: str, action_name: str, direction: str, schema: dict, schema_id: str
) -> None:
    _exec_psql(
        dsn,
        "CALL wf.wf_repo_upsert_action_schema("
        f"{_sql_literal(action_name)}, "
        f"{_sql_literal(direction)}, "
        f"{_json_literal(schema)}, "
        f"{_sql_literal(schema_id)});",
    )


def _seed_via_admin_gateway() -> tuple[int, int]:
    from rest.admin_client import admin_request, load_catalog_seed_payload

    if not CATALOG_PATH.is_file():
        raise SystemExit(f"Missing {CATALOG_PATH}; run methyl-export-action-catalog first.")
    if not TASKS_DIR.is_dir():
        raise SystemExit(f"Missing {TASKS_DIR}; run methyl-export-task-schemas first.")

    payload = load_catalog_seed_payload(CATALOG_PATH, TASKS_DIR)
    result = admin_request("POST", "/admin/catalog/seed", payload)
    action_count = int(result.get("actions_upserted") or 0)
    schema_count = int(result.get("schemas_upserted") or 0)
    errors = result.get("errors") or []
    for err in errors:
        print(f"Seed warning: {err}", file=sys.stderr)
    for action in payload["catalog"].get("actions") or []:
        print(f"Upserted action {action['action_name']}")
    return action_count, schema_count


def _seed_via_gateway() -> tuple[int, int]:
    from rest.connection import resolve_connection_config
    from rest.db import open_gateway_db
    from rest.db_client import upsert_action_schema, upsert_workflow_action

    config = resolve_connection_config()
    db = open_gateway_db(config)
    try:
        if not CATALOG_PATH.is_file():
            raise SystemExit(f"Missing {CATALOG_PATH}; run methyl-export-action-catalog first.")

        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        actions = catalog.get("actions") or []

        action_count = 0
        for action in actions:
            upsert_workflow_action(
                db,
                str(action["action_name"]),
                str(action.get("capability") or "") or None,
                str(action.get("schema_id") or action["action_name"]),
                execution_mode=action.get("execution_mode"),
                cli_tool=action.get("cli_tool"),
                in_process_handler=action.get("in_process_handler"),
                argv_map=action.get("argv_map") if isinstance(action.get("argv_map"), dict) else None,
            )
            action_count += 1
            print(f"Upserted action {action['action_name']}")

        if not TASKS_DIR.is_dir():
            raise SystemExit(f"Missing {TASKS_DIR}; run methyl-export-task-schemas first.")

        schema_count = 0
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
                upsert_action_schema(db, spec.action_name, direction, schema, spec.schema_id)
                schema_count += 1
                print(f"Upserted schema {spec.action_name} ({direction})")

        return action_count, schema_count
    finally:
        db.close()


def _seed_via_psql(dsn: str) -> tuple[int, int]:
    if not CATALOG_PATH.is_file():
        raise SystemExit(f"Missing {CATALOG_PATH}; run methyl-export-action-catalog first.")

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    actions = catalog.get("actions") or []

    action_count = 0
    for action in actions:
        _upsert_action_psql(
            dsn,
            str(action["action_name"]),
            str(action.get("capability") or ""),
            str(action.get("schema_id") or action["action_name"]),
            execution_mode=action.get("execution_mode"),
            cli_tool=action.get("cli_tool"),
            in_process_handler=action.get("in_process_handler"),
            argv_map=action.get("argv_map") if isinstance(action.get("argv_map"), dict) else None,
        )
        action_count += 1
        print(f"Upserted action {action['action_name']}")

    if not TASKS_DIR.is_dir():
        raise SystemExit(f"Missing {TASKS_DIR}; run methyl-export-task-schemas first.")

    schema_count = 0
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
            _upsert_schema_psql(dsn, spec.action_name, direction, schema, spec.schema_id)
            schema_count += 1
            print(f"Upserted schema {spec.action_name} ({direction})")

    return action_count, schema_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed wf.workflow_action + schemas from schemas/actions/catalog.json"
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help=(
            "PostgreSQL DSN only (skip gateway env; uses psql). "
            "Requires wf_action_dispatch_metadata.sql so the 7-arg upsert exists."
        ),
    )
    parser.add_argument(
        "--regenerate-catalog",
        action="store_true",
        help="Run methyl-export-action-catalog before seeding",
    )
    parser.add_argument(
        "--use-gateway",
        action="store_true",
        help="Seed via admin REST gateway (requires WORKER_API_BASE + GATEWAY_ADMIN_BEARER_TOKEN)",
    )
    parser.add_argument(
        "--use-db",
        action="store_true",
        help="Seed via direct DB connection (default when no admin token)",
    )
    args = parser.parse_args(argv)

    if args.regenerate_catalog:
        export_action_catalog(write=True)

    import os

    use_gateway = args.use_gateway or (
        not args.dsn
        and not args.use_db
        and bool(os.environ.get("GATEWAY_ADMIN_BEARER_TOKEN") or os.environ.get("GATEWAY_ENTRA_BEARER_TOKEN"))
    )

    if args.dsn:
        action_count, schema_count = _seed_via_psql(args.dsn)
    elif use_gateway:
        action_count, schema_count = _seed_via_admin_gateway()
    else:
        action_count, schema_count = _seed_via_gateway()

    print(f"Seeded {action_count} action(s) and {schema_count} schema(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
