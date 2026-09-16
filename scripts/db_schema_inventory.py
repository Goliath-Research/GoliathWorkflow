#!/usr/bin/env python3
"""
Live object inventory: Azure SQL vs PostgreSQL for controlled schemas.

Compares tables, views, routines, and cross-schema FKs for:
  wf, cfg, portal, RBAC, Meta, Contract, Onboarding

Usage:
  source .venv/bin/activate

  # Both backends (writes JSON + markdown under workflow_engine/contract/)
  export AZURE_SQL_SERVER=... AZURE_SQL_DB=MethylPipeline AZURE_SQL_USER=... AZURE_SQL_PASSWORD=...
  export POSTGRES_HOST=goliath.postgres.database.azure.com POSTGRES_DB=goliath \\
         POSTGRES_USER=dba POSTGRES_PASSWORD='...' PGSSLMODE=require
  python scripts/db_schema_inventory.py

  # One side only
  python scripts/db_schema_inventory.py --backend mssql
  python scripts/db_schema_inventory.py --backend postgres

Exit 0 always when inventory succeeds; exit 1 if --fail-on-gap and controlled
objects exist on Azure SQL without a PostgreSQL twin (tables/routines).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "workflow_engine" / "contract"
CONTROLLED_SCHEMAS = (
    "wf",
    "cfg",
    "portal",
    "RBAC",
    "Meta",
    "Contract",
    "Onboarding",
)
# Diagram / SSMS junk — never part of the twin.
SKIP_ROUTINE_PREFIXES = (
    "sp_alterdiagram",
    "sp_creatediagram",
    "sp_dropdiagram",
    "sp_helpdiagram",
    "sp_renamediagram",
    "sp_upgraddiagrams",
    "fn_diagramobjects",
)


@dataclass
class Inventory:
    backend: str
    database: str
    captured_at_utc: str
    tables: Dict[str, List[str]] = field(default_factory=dict)
    views: Dict[str, List[str]] = field(default_factory=dict)
    routines: Dict[str, List[str]] = field(default_factory=dict)
    cross_schema_fks: List[Dict[str, str]] = field(default_factory=list)

    def normalized_tables(self) -> Set[str]:
        out: Set[str] = set()
        for schema, names in self.tables.items():
            for name in names:
                out.add(f"{schema}.{name}".lower())
        return out

    def normalized_routines(self) -> Set[str]:
        out: Set[str] = set()
        for schema, names in self.routines.items():
            for name in names:
                if any(name.lower().startswith(p) for p in SKIP_ROUTINE_PREFIXES):
                    continue
                out.add(f"{schema}.{name}".lower())
        return out


def _mssql_connect():
    import pyodbc  # type: ignore

    server = os.environ.get("AZURE_SQL_SERVER", "")
    database = os.environ.get("AZURE_SQL_DB", "MethylPipeline")
    user = os.environ.get("AZURE_SQL_USER", "")
    password = os.environ.get("AZURE_SQL_PASSWORD", "")
    if not server or not user or not password:
        raise SystemExit(
            "Set AZURE_SQL_SERVER, AZURE_SQL_USER, AZURE_SQL_PASSWORD "
            "(and optionally AZURE_SQL_DB)."
        )
    drivers = [d for d in pyodbc.drivers() if "ODBC Driver" in d and "SQL Server" in d]
    driver = drivers[-1] if drivers else "ODBC Driver 18 for SQL Server"
    conn_str = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"UID={user};PWD={password};Encrypt=yes;TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=30), database


def _pg_connect():
    import psycopg  # type: ignore

    host = os.environ.get("POSTGRES_HOST") or os.environ.get("PGHOST", "")
    port = os.environ.get("POSTGRES_PORT") or os.environ.get("PGPORT", "5432")
    database = (
        os.environ.get("POSTGRES_DB")
        or os.environ.get("PGDATABASE")
        or "goliath"
    )
    user = os.environ.get("POSTGRES_USER") or os.environ.get("PGUSER", "")
    password = os.environ.get("POSTGRES_PASSWORD") or os.environ.get("PGPASSWORD", "")
    sslmode = os.environ.get("PGSSLMODE", "require")
    if not host or not user:
        raise SystemExit(
            "Set POSTGRES_HOST/PGHOST and POSTGRES_USER/PGUSER "
            "(and POSTGRES_PASSWORD/PGPASSWORD)."
        )
    conn = psycopg.connect(
        host=host,
        port=int(port),
        dbname=database,
        user=user,
        password=password or None,
        sslmode=sslmode,
        connect_timeout=30,
    )
    return conn, database


def _schema_list_sql_literals() -> str:
    return ", ".join(f"'{s}'" for s in CONTROLLED_SCHEMAS)


def inventory_mssql() -> Inventory:
    conn, database = _mssql_connect()
    schemas = _schema_list_sql_literals()
    inv = Inventory(
        backend="mssql",
        database=database,
        captured_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT s.name, t.name
            FROM sys.tables t
            JOIN sys.schemas s ON s.schema_id = t.schema_id
            WHERE s.name IN ({schemas})
            ORDER BY s.name, t.name
            """
        )
        for schema, name in cur.fetchall():
            inv.tables.setdefault(schema, []).append(name)

        cur.execute(
            f"""
            SELECT s.name, v.name
            FROM sys.views v
            JOIN sys.schemas s ON s.schema_id = v.schema_id
            WHERE s.name IN ({schemas})
            ORDER BY s.name, v.name
            """
        )
        for schema, name in cur.fetchall():
            inv.views.setdefault(schema, []).append(name)

        cur.execute(
            f"""
            SELECT SCHEMA_NAME(o.schema_id), o.name
            FROM sys.objects o
            WHERE o.type IN ('P', 'FN', 'IF', 'TF', 'FS', 'FT')
              AND SCHEMA_NAME(o.schema_id) IN ({schemas})
            ORDER BY SCHEMA_NAME(o.schema_id), o.name
            """
        )
        for schema, name in cur.fetchall():
            inv.routines.setdefault(schema, []).append(name)

        cur.execute(
            f"""
            SELECT fk.name,
                   SCHEMA_NAME(pt.schema_id), pt.name,
                   SCHEMA_NAME(rt.schema_id), rt.name
            FROM sys.foreign_keys fk
            JOIN sys.tables pt ON pt.object_id = fk.parent_object_id
            JOIN sys.tables rt ON rt.object_id = fk.referenced_object_id
            WHERE SCHEMA_NAME(pt.schema_id) IN ({schemas})
              AND SCHEMA_NAME(rt.schema_id) IN ({schemas})
              AND SCHEMA_NAME(pt.schema_id) <> SCHEMA_NAME(rt.schema_id)
            ORDER BY fk.name
            """
        )
        for fk_name, p_schema, p_table, r_schema, r_table in cur.fetchall():
            inv.cross_schema_fks.append(
                {
                    "fk_name": fk_name,
                    "parent": f"{p_schema}.{p_table}",
                    "referenced": f"{r_schema}.{r_table}",
                }
            )
    finally:
        conn.close()
    return inv


def inventory_postgres() -> Inventory:
    conn, database = _pg_connect()
    inv = Inventory(
        backend="postgres",
        database=database,
        captured_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    # PG folds unquoted identifiers; also match quoted PascalCase via pg_catalog.
    schema_filter = ", ".join(
        f"'{s}'" for s in CONTROLLED_SCHEMAS
    ) + ", " + ", ".join(f"'{s.lower()}'" for s in CONTROLLED_SCHEMAS)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT n.nspname, c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r'
                  AND n.nspname IN ({schema_filter})
                ORDER BY n.nspname, c.relname
                """
            )
            for schema, name in cur.fetchall():
                inv.tables.setdefault(schema, []).append(name)

            cur.execute(
                f"""
                SELECT n.nspname, c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'v'
                  AND n.nspname IN ({schema_filter})
                ORDER BY n.nspname, c.relname
                """
            )
            for schema, name in cur.fetchall():
                inv.views.setdefault(schema, []).append(name)

            cur.execute(
                f"""
                SELECT n.nspname, p.proname
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname IN ({schema_filter})
                  AND p.prokind IN ('f', 'p')
                ORDER BY n.nspname, p.proname
                """
            )
            for schema, name in cur.fetchall():
                inv.routines.setdefault(schema, []).append(name)

            cur.execute(
                f"""
                SELECT tc.constraint_name,
                       tc.table_schema, tc.table_name,
                       ccu.table_schema, ccu.table_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.constraint_schema = tc.constraint_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema IN ({schema_filter})
                  AND ccu.table_schema IN ({schema_filter})
                  AND tc.table_schema <> ccu.table_schema
                ORDER BY tc.constraint_name
                """
            )
            for fk_name, p_schema, p_table, r_schema, r_table in cur.fetchall():
                inv.cross_schema_fks.append(
                    {
                        "fk_name": fk_name,
                        "parent": f"{p_schema}.{p_table}",
                        "referenced": f"{r_schema}.{r_table}",
                    }
                )
    finally:
        conn.close()
    return inv


def _canon_schema(name: str) -> str:
    """Map PG lowercase schema names back to controlled casing."""
    lower_map = {s.lower(): s for s in CONTROLLED_SCHEMAS}
    return lower_map.get(name, name)


def diff_inventories(
    mssql: Optional[Inventory], postgres: Optional[Inventory]
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "mssql": asdict(mssql) if mssql else None,
        "postgres": asdict(postgres) if postgres else None,
        "gaps": {},
    }
    if not mssql or not postgres:
        return result

    mssql_tables = mssql.normalized_tables()
    pg_tables = postgres.normalized_tables()
    # Ignore PG-only test bed.
    pg_ignore = {
        "wf.test_bed_run",
        "wf.test_bed_task_log",
        "wf.foreach_bundle_entry",
    }
    mssql_routines = mssql.normalized_routines()
    pg_routines = postgres.normalized_routines()

    result["gaps"] = {
        "tables_mssql_only": sorted(mssql_tables - pg_tables),
        "tables_postgres_only": sorted(pg_tables - mssql_tables - pg_ignore),
        "routines_mssql_only": sorted(mssql_routines - pg_routines),
        "routines_postgres_only": sorted(
            r
            for r in (pg_routines - mssql_routines)
            if not r.startswith("wf.wf_test_bed")
            and not r.startswith("wf.sp_test_bed")
            and r
            not in {
                "wf.wf_json_path_to_segments",
                "wf.wf_json_set_path",
                "wf.wf_json_path_to_pg",
                "wf.wf_json_unquote_string",
                "wf.wf_try_read_json_file",
                "wf.wf_json_encode_jsonb_value",
                "cfg._content_hash",
                "cfg.cfg_repo_get",
                "cfg.cfg_repo_list",
                "cfg.cfg_repo_get_credential_secret",
            }
        ),
        "cross_schema_fks_mssql_count": len(mssql.cross_schema_fks),
        "cross_schema_fks_postgres_count": len(postgres.cross_schema_fks),
    }
    return result


def _merge_case_variants(bucket: Dict[str, List[str]], schema: str) -> List[str]:
    """Union table/routine names across PascalCase and lowercase schema keys.

    For already-lowercase schemas (wf, cfg, portal), ``schema`` and
    ``schema.lower()`` are the same dict key — do not concatenate the list twice.
    """
    primary = list(bucket.get(schema, []))
    lower = schema.lower()
    if lower == schema:
        return primary
    seen = set(primary)
    for name in bucket.get(lower, []):
        if name not in seen:
            primary.append(name)
            seen.add(name)
    return primary


def write_outputs(payload: Dict[str, Any]) -> Tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "schema_inventory_live.json"
    md_path = OUT_DIR / "schema_inventory_live.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    gaps = payload.get("gaps") or {}
    lines = [
        "# Live schema inventory (Azure SQL vs PostgreSQL)",
        "",
        f"Captured: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "Controlled schemas: "
        + ", ".join(f"`{s}`" for s in CONTROLLED_SCHEMAS)
        + ".",
        "",
    ]
    if payload.get("mssql"):
        m = payload["mssql"]
        lines.append(f"## Azure SQL (`{m['database']}`)")
        lines.append("")
        for schema in CONTROLLED_SCHEMAS:
            tables = m["tables"].get(schema, [])
            routines = m["routines"].get(schema, [])
            lines.append(
                f"- `{schema}`: {len(tables)} tables, {len(routines)} routines"
            )
        lines.append("")
    if payload.get("postgres"):
        p = payload["postgres"]
        lines.append(f"## PostgreSQL (`{p['database']}`)")
        lines.append("")
        for schema in CONTROLLED_SCHEMAS:
            tables = _merge_case_variants(p["tables"], schema)
            routines = _merge_case_variants(p["routines"], schema)
            lines.append(
                f"- `{schema}`: {len(tables)} tables, {len(routines)} routines"
            )
        lines.append("")
        lines.append(
            "> Note: the Azure PG database named `postgres` is a stale older "
            "wf-only deploy. Canonical parity target is **`goliath`**."
        )
        lines.append("")
    if gaps:
        lines.append("## Gaps (MSSQL − PostgreSQL)")
        lines.append("")
        for key in (
            "tables_mssql_only",
            "tables_postgres_only",
            "routines_mssql_only",
            "routines_postgres_only",
        ):
            items = gaps.get(key) or []
            lines.append(f"### `{key}` ({len(items)})")
            lines.append("")
            if not items:
                lines.append("_none_")
            else:
                for item in items[:200]:
                    lines.append(f"- `{item}`")
                if len(items) > 200:
                    lines.append(f"- … and {len(items) - 200} more")
            lines.append("")
        lines.append(
            f"Cross-schema FKs: MSSQL={gaps.get('cross_schema_fks_mssql_count', 0)}, "
            f"PostgreSQL={gaps.get('cross_schema_fks_postgres_count', 0)}"
        )
        lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=("both", "mssql", "postgres"),
        default="both",
    )
    parser.add_argument(
        "--fail-on-gap",
        action="store_true",
        help="Exit 1 when Azure SQL has controlled tables/routines missing on PG.",
    )
    args = parser.parse_args()

    mssql_inv: Optional[Inventory] = None
    pg_inv: Optional[Inventory] = None
    if args.backend in ("both", "mssql"):
        print("Inventorying Azure SQL …", flush=True)
        mssql_inv = inventory_mssql()
    if args.backend in ("both", "postgres"):
        print("Inventorying PostgreSQL …", flush=True)
        pg_inv = inventory_postgres()

    payload = diff_inventories(mssql_inv, pg_inv)
    json_path, md_path = write_outputs(payload)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")

    if args.fail_on_gap and mssql_inv and pg_inv:
        gaps = payload["gaps"]
        if gaps.get("tables_mssql_only") or gaps.get("routines_mssql_only"):
            print(
                f"FAIL: {len(gaps.get('tables_mssql_only') or [])} tables and "
                f"{len(gaps.get('routines_mssql_only') or [])} routines on "
                "Azure SQL without PostgreSQL twin.",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
