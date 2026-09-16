#!/usr/bin/env python3
"""
Populate PostgreSQL wf **action catalog** (and optional workflow definitions).

Despite the historic script name, this does **not** seed genome / cfg.reference_asset
rows. For genomes use ``cfg_reference_assets_seed.sql`` (via ``sql_pg/deploy_azure.sh``)
plus provision from myQNAPcloud — see ``docs/deployment/reference-inventory-qnap.md``.

Azure SQL is the production database (populated, in use). PostgreSQL typically has
the same schema/procedures but empty wf action tables. Canonical PG database is
``goliath`` (not the stale ``postgres`` database on the same server). This script:

  1. Seeds action catalog + JSON schemas from the **git repo** (current catalog).
  2. Optionally copies workflow **definitions** (def/version/node/edge/bindings) from
     Azure SQL when both connection env sets are available.

Does NOT copy runtime data (instances, executions, workers, leases) and does NOT
seed ``cfg.reference_asset`` / storage endpoints.

Usage:
  source .venv/bin/activate

  # Catalog only (POSTGRES_* required)
  export POSTGRES_HOST=... POSTGRES_DB=goliath POSTGRES_USER=dba POSTGRES_PASSWORD='...'
  export PGSSLMODE=require
  python scripts/populate_postgres_reference_data.py

  # Catalog + workflow definitions cloned from Azure SQL
  export AZURE_SQL_SERVER=... AZURE_SQL_DB=... AZURE_SQL_USER=... AZURE_SQL_PASSWORD='...'
  python scripts/populate_postgres_reference_data.py --workflows-from-mssql

  # Inspect Azure SQL via Cursor MCP (user-azure-sql-dev) without running this script.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
WF_ENGINE = REPO_ROOT / "workflow_engine"
sys.path.insert(0, str(REPO_ROOT / "workers"))
sys.path.insert(0, str(WF_ENGINE))

# Graph tables only (catalog seeded separately from repo).
_GRAPH_TABLES: Sequence[str] = (
    "workflow_def",
    "workflow_version",
    "workflow_node",
    "workflow_edge",
    "workflow_input_template",
    "workflow_input_binding",
    "variable_output_binding",
    "node_scope_default",
    "workflow_collection_binding",
)

# Tables copied MSSQL → PG (definition graph only).
_WORKFLOW_TABLES = _GRAPH_TABLES

# Child-first truncate on PostgreSQL (workflow graph only — not action catalog).
_PG_TRUNCATE_GRAPH = """
TRUNCATE TABLE
  wf.workflow_collection_binding,
  wf.workflow_input_binding,
  wf.variable_output_binding,
  wf.node_scope_default,
  wf.workflow_input_template,
  wf.workflow_edge,
  wf.workflow_node,
  wf.workflow_version,
  wf.workflow_def
RESTART IDENTITY CASCADE;
"""


def _pg_conninfo() -> str:
    from rest.connection import build_postgres_conninfo

    return build_postgres_conninfo(use_managed_identity=os.environ.get("WF_USE_MANAGED_IDENTITY", "").lower() in ("1", "true"))


def _mssql_conninfo() -> str:
    from rest.connection import build_mssql_conninfo

    return build_mssql_conninfo(use_managed_identity=os.environ.get("WF_USE_MANAGED_IDENTITY", "").lower() in ("1", "true"))


def _seed_catalog_from_repo() -> None:
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "workflow_engine/sql_mssql/seed_action_catalog.py"),
            "--regenerate-catalog",
            "--use-db",
        ],
        check=True,
        env={**os.environ, "BACKEND_DB": "postgres"},
    )


def _table_exists_mssql(cur: Any, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'wf' AND TABLE_NAME = ?",
        (table,),
    )
    return cur.fetchone() is not None


def _fetch_mssql_table(cur: Any, table: str) -> tuple[List[str], List[tuple]]:
    cur.execute(f"SELECT * FROM wf.{table}")
    columns = [col[0] for col in cur.description]
    rows = cur.fetchall()
    return columns, rows


def _pg_insert_rows(pg: Any, table: str, columns: List[str], rows: Iterable[tuple]) -> int:
    if not rows:
        return 0
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = (
        f"INSERT INTO wf.{table} ({col_list}) OVERRIDING SYSTEM VALUE "
        f"VALUES ({placeholders})"
    )
    count = 0
    with pg.cursor() as cur:
        for row in rows:
            cur.execute(sql, row)
            count += 1
    return count


def _pg_action_id_map(pg: Any) -> Dict[str, int]:
    with pg.cursor() as cur:
        cur.execute("SELECT id, action_name FROM wf.workflow_action")
        return {str(row[1]): int(row[0]) for row in cur.fetchall()}


def _mssql_action_id_to_name(cur: Any) -> Dict[int, str]:
    cur.execute("SELECT id, action_name FROM wf.workflow_action")
    return {int(row[0]): str(row[1]) for row in cur.fetchall()}


def _remap_node_action_ids(
    columns: List[str],
    rows: List[tuple],
    mssql_ids: Dict[int, str],
    pg_by_name: Dict[str, int],
) -> List[tuple]:
    if "workflow_action_id" not in columns:
        return rows
    idx = columns.index("workflow_action_id")
    out: List[tuple] = []
    for row in rows:
        row_list = list(row)
        old_id = row_list[idx]
        if old_id is not None:
            name = mssql_ids.get(int(old_id))
            if name and name in pg_by_name:
                row_list[idx] = pg_by_name[name]
            else:
                row_list[idx] = None
        out.append(tuple(row_list))
    return out


def _sync_workflows_mssql_to_postgres() -> Dict[str, int]:
    import psycopg
    import pyodbc

    mssql = pyodbc.connect(_mssql_conninfo())
    counts: Dict[str, int] = {}
    try:
        mcur = mssql.cursor()
        mssql_action_ids = _mssql_action_id_to_name(mcur)
        payloads: Dict[str, tuple[List[str], List[tuple]]] = {}
        for table in _GRAPH_TABLES:
            if not _table_exists_mssql(mcur, table):
                continue
            payloads[table] = _fetch_mssql_table(mcur, table)

        version_root: Dict[int, Any] = {}
        if "workflow_version" in payloads:
            vcols, vrows = payloads["workflow_version"]
            if "root_node_id" in vcols:
                ridx = vcols.index("root_node_id")
                vid_idx = vcols.index("id")
                for row in vrows:
                    version_root[int(row[vid_idx])] = row[ridx]
                vcols_noroot = [c for c in vcols if c != "root_node_id"]
                payloads["workflow_version"] = (
                    vcols_noroot,
                    [tuple(row[i] for i, c in enumerate(vcols) if c != "root_node_id") for row in vrows],
                )

        with psycopg.connect(_pg_conninfo()) as pg:
            with pg.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM wf.workflow_instance")
                inst = int(cur.fetchone()[0])
                if inst > 0:
                    raise SystemExit(
                        "PostgreSQL has workflow_instance rows; refusing to truncate definition tables. "
                        "Use a fresh PG database or delete instances first."
                    )
                cur.execute(_PG_TRUNCATE_GRAPH)

            insert_order = (
                "workflow_def",
                "workflow_version",
                "workflow_node",
                "workflow_edge",
                "workflow_input_template",
                "workflow_input_binding",
                "variable_output_binding",
                "node_scope_default",
                "workflow_collection_binding",
            )
            for table in insert_order:
                if table not in payloads:
                    continue
                columns, rows = payloads[table]
                if table == "workflow_node":
                    pg_map = _pg_action_id_map(pg)
                    rows = _remap_node_action_ids(columns, list(rows), mssql_action_ids, pg_map)
                counts[table] = _pg_insert_rows(pg, table, columns, rows)

            if version_root:
                with pg.cursor() as cur:
                    for ver_id, root_id in version_root.items():
                        if root_id is None:
                            continue
                        cur.execute(
                            "UPDATE wf.workflow_version SET root_node_id = %s WHERE id = %s",
                            (root_id, ver_id),
                        )
            pg.commit()
    finally:
        mssql.close()
    return counts


def _sync_portal_profiles() -> int:
    import psycopg
    import pyodbc

    mssql = pyodbc.connect(_mssql_conninfo())
    try:
        mcur = mssql.cursor()
        mcur.execute(
            "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'portal' AND TABLE_NAME = 'resource_profile'"
        )
        if not mcur.fetchone():
            return 0
        mcur.execute("SELECT profile_key, profile_type, profile_json, status FROM portal.resource_profile")
        rows = mcur.fetchall()
    finally:
        mssql.close()

    if not rows:
        return 0

    import psycopg

    with psycopg.connect(_pg_conninfo()) as pg:
        with pg.cursor() as cur:
            for key, ptype, pjson, status in rows:
                payload = pjson if isinstance(pjson, str) else json.dumps(pjson)
                cur.execute(
                    """
                    INSERT INTO portal.resource_profile (profile_key, profile_type, profile_json, status)
                    VALUES (%s, %s, %s::jsonb, %s)
                    ON CONFLICT (profile_key) DO UPDATE SET
                      profile_type = EXCLUDED.profile_type,
                      profile_json = EXCLUDED.profile_json,
                      status = EXCLUDED.status
                    """,
                    (key, ptype, payload, status),
                )
        pg.commit()
    return len(rows)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--skip-catalog",
        action="store_true",
        help="Skip repo catalog seed (only when --workflows-from-mssql and catalog already present)",
    )
    parser.add_argument(
        "--workflows-from-mssql",
        action="store_true",
        help="Copy workflow definition tables from Azure SQL to PostgreSQL",
    )
    parser.add_argument(
        "--portal-profiles-from-mssql",
        action="store_true",
        help="Upsert portal.resource_profile rows from Azure SQL",
    )
    args = parser.parse_args(argv)

    if not args.skip_catalog:
        print("Seeding action catalog + task schemas from repo → PostgreSQL ...")
        _seed_catalog_from_repo()

    if args.workflows_from_mssql:
        for var in ("AZURE_SQL_SERVER", "AZURE_SQL_DB", "AZURE_SQL_USER", "AZURE_SQL_PASSWORD"):
            if not os.environ.get(var) and not os.environ.get("METHYLPIPELINE_DB"):
                raise SystemExit(f"Missing {var} for --workflows-from-mssql")
        print("Copying workflow definitions Azure SQL → PostgreSQL ...")
        counts = _sync_workflows_mssql_to_postgres()
        for table, n in counts.items():
            print(f"  {table}: {n} rows")

    if args.portal_profiles_from_mssql:
        n = _sync_portal_profiles()
        print(f"portal.resource_profile: {n} rows upserted")

    print("Done.")
    print("Next: point gateway at PostgreSQL (BACKEND_DB=postgres), deploy workflows if not cloned:")
    print("  bash scripts/deploy_workflow_definitions.sh --api-base http://localhost:8080/v1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
