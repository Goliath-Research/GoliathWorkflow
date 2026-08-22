#!/usr/bin/env python3
"""
Extract incremental, idempotent MSSQL schema scripts from MethylPipeline.sql
and (optionally) script missing live tables from Azure SQL via pyodbc.

Writes under workflow_engine/sql_mssql/:
  meta_schema.sql, meta_api.sql
  rbac_schema.sql, rbac_api.sql
  portal_clinical_schema.sql, portal_clinical_api.sql
  contract_schema.sql, contract_api.sql
  onboarding_schema.sql, onboarding_api.sql

Usage:
  source .venv/bin/activate
  python scripts/extract_legacy_schema.py
  # also script live extras (DiseaseFieldContract, …):
  python scripts/extract_legacy_schema.py --from-live
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
MONOLITH = REPO / "workflow_engine" / "sql_mssql" / "MethylPipeline.sql"
OUT_DIR = REPO / "workflow_engine" / "sql_mssql"

SCHEMA_ORDER = ("Meta", "RBAC", "portal", "Contract", "Onboarding")

# Tables already owned by incremental parity scripts — skip from clinical extract.
PORTAL_SKIP_TABLES = {"resource_profile", "sample_field_contract"}


def _split_go_batches(text: str) -> List[str]:
    # Split on GO at line start (case-insensitive), keep non-empty.
    parts = re.split(r"(?im)^\s*GO\s*$", text)
    return [p.strip("\n") for p in parts if p.strip()]


def _strip_leading_noise(batch: str) -> str:
    """Remove leading PRINT, line comments, and block comments so CREATE is visible."""
    text = batch.lstrip()
    while True:
        if text.startswith("PRINT"):
            nl = text.find("\n")
            text = text[nl + 1 :].lstrip() if nl >= 0 else ""
            continue
        if text.startswith("--"):
            nl = text.find("\n")
            text = text[nl + 1 :].lstrip() if nl >= 0 else ""
            continue
        if text.startswith("/*"):
            end = text.find("*/")
            if end < 0:
                break
            text = text[end + 2 :].lstrip()
            continue
        break
    return text


def _object_kind(batch: str) -> Optional[Tuple[str, str, str]]:
    """Return (kind, schema, name) for CREATE TABLE / PROC / FUNCTION / INDEX / ALTER FK."""
    body = _strip_leading_noise(batch)
    m = re.match(
        r"(?is)CREATE\s+TABLE\s+(?:\[?(\w+)\]?\.)?\[?(\w+)\]?",
        body,
    )
    if m:
        schema = m.group(1) or "dbo"
        return ("table", schema, m.group(2))

    m = re.match(
        r"(?is)CREATE\s+OR\s+ALTER\s+(PROCEDURE|FUNCTION|TRIGGER)\s+(?:\[?(\w+)\]?\.)?\[?(\w+)\]?",
        body,
    )
    if m:
        kind_map = {
            "PROCEDURE": "procedure",
            "FUNCTION": "function",
            "TRIGGER": "trigger",
        }
        schema = m.group(2) or "dbo"
        return (kind_map[m.group(1).upper()], schema, m.group(3))

    m = re.match(
        r"(?is)CREATE\s+(UNIQUE\s+)?(?:NONCLUSTERED\s+|CLUSTERED\s+)?INDEX\s+\[?\w+\]?\s+ON\s+(?:\[?(\w+)\]?\.)?\[?(\w+)\]?",
        body,
    )
    if m:
        schema = m.group(2) or "dbo"
        return ("index", schema, m.group(3))

    m = re.match(
        r"(?is)ALTER\s+TABLE\s+(?:\[?(\w+)\]?\.)?\[?(\w+)\]?\s+ADD\s+CONSTRAINT",
        body,
    )
    if m:
        schema = m.group(1) or "dbo"
        return ("fk", schema, m.group(2))

    m = re.match(r"(?is)CREATE\s+SCHEMA\s+\[?(\w+)\]?", body)
    if m:
        return ("schema", m.group(1), m.group(1))

    return None


def _make_table_idempotent(batch: str, schema: str, name: str) -> str:
    # Strip leading PRINT / comments noise but keep CREATE TABLE body.
    body = batch.strip()
    # Remove trailing GO remnants
    body = re.sub(r"(?im)^\s*PRINT\s+N'[^']*'\s*;?\s*$", "", body)
    body = body.strip()
    return (
        f"IF OBJECT_ID(N'{schema}.{name}', N'U') IS NULL\n"
        f"BEGIN\n"
        f"{body}\n"
        f"END\n"
        f"GO\n"
    )


def _make_index_idempotent(batch: str) -> str:
    m = re.search(
        r"(?is)CREATE\s+(UNIQUE\s+)?(NONCLUSTERED\s+|CLUSTERED\s+)?INDEX\s+(\[?\w+\]?)\s+ON",
        batch,
    )
    if not m:
        return batch.strip() + "\nGO\n"
    idx = m.group(3).strip("[]")
    body = re.sub(r"(?im)^\s*PRINT\s+N'[^']*'\s*;?\s*$", "", batch).strip()
    return (
        f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'{idx}' AND object_id IS NOT NULL)\n"
        f"BEGIN\n"
        f"  {body}\n"
        f"END\n"
        f"GO\n"
    )


def _make_fk_idempotent(batch: str) -> str:
    m = re.search(r"(?is)ADD\s+CONSTRAINT\s+(\[?\w+\]?)", batch)
    if not m:
        return batch.strip() + "\nGO\n"
    cname = m.group(1).strip("[]")
    body = re.sub(r"(?im)^\s*PRINT\s+N'[^']*'\s*;?\s*$", "", batch).strip()
    return (
        f"IF OBJECT_ID(N'{cname}', N'F') IS NULL AND NOT EXISTS (\n"
        f"  SELECT 1 FROM sys.foreign_keys WHERE name = N'{cname}'\n"
        f")\n"
        f"BEGIN\n"
        f"  {body}\n"
        f"END\n"
        f"GO\n"
    )


def _clean_routine(batch: str) -> str:
    body = re.sub(r"(?im)^\s*PRINT\s+N'[^']*'\s*;?\s*$", "", batch).strip()
    # Already CREATE OR ALTER — keep as-is
    if not re.search(r"(?is)^CREATE\s+OR\s+ALTER", body):
        body = re.sub(
            r"(?is)^CREATE\s+(PROCEDURE|FUNCTION)",
            r"CREATE OR ALTER \1",
            body,
            count=1,
        )
    return body + "\nGO\n"


def extract_from_monolith() -> Dict[str, Dict[str, List[str]]]:
    text = MONOLITH.read_text(encoding="utf-8", errors="replace")
    batches = _split_go_batches(text)
    buckets: Dict[str, Dict[str, List[str]]] = {
        s: {"schema_ddl": [], "api": []} for s in SCHEMA_ORDER
    }

    for batch in batches:
        info = _object_kind(batch)
        if not info:
            continue
        kind, schema, name = info
        if schema not in buckets:
            continue
        if kind == "schema":
            buckets[schema]["schema_ddl"].append(
                f"IF SCHEMA_ID(N'{schema}') IS NULL EXEC(N'CREATE SCHEMA [{schema}]');\nGO\n"
            )
        elif kind == "table":
            if schema == "portal" and name in PORTAL_SKIP_TABLES:
                continue
            # Skip wf tables entirely (handled elsewhere)
            buckets[schema]["schema_ddl"].append(
                _make_table_idempotent(batch, schema, name)
            )
        elif kind == "index":
            buckets[schema]["schema_ddl"].append(_make_index_idempotent(batch))
        elif kind == "fk":
            buckets[schema]["schema_ddl"].append(_make_fk_idempotent(batch))
        elif kind in ("procedure", "function", "trigger"):
            buckets[schema]["api"].append(_clean_routine(batch))
    return buckets


def script_live_tables(schemas: List[str]) -> Dict[str, str]:
    """Generate IF OBJECT_ID CREATE TABLE scripts from live Azure SQL."""
    import pyodbc

    drivers = [d for d in pyodbc.drivers() if "ODBC Driver" in d and "SQL Server" in d]
    driver = drivers[-1] if drivers else "ODBC Driver 18 for SQL Server"
    server = os.environ["AZURE_SQL_SERVER"]
    database = os.environ.get("AZURE_SQL_DB", "MethylPipeline")
    user = os.environ["AZURE_SQL_USER"]
    password = os.environ["AZURE_SQL_PASSWORD"]
    cn = pyodbc.connect(
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"UID={user};PWD={password};Encrypt=yes;TrustServerCertificate=yes;"
    )
    out: Dict[str, str] = {}
    try:
        cur = cn.cursor()
        for schema in schemas:
            cur.execute(
                """
                SELECT t.name
                FROM sys.tables t
                JOIN sys.schemas s ON s.schema_id = t.schema_id
                WHERE s.name = ?
                ORDER BY t.name
                """,
                schema,
            )
            tables = [r[0] for r in cur.fetchall()]
            parts = [
                f"IF SCHEMA_ID(N'{schema}') IS NULL EXEC(N'CREATE SCHEMA [{schema}]');\nGO\n"
            ]
            for table in tables:
                if schema == "portal" and table in PORTAL_SKIP_TABLES:
                    continue
                cur.execute(
                    """
                    SELECT c.name, ty.name AS type_name, c.max_length, c.precision, c.scale,
                           c.is_nullable, c.is_identity,
                           dc.definition AS default_def
                    FROM sys.columns c
                    JOIN sys.types ty ON ty.user_type_id = c.user_type_id
                    LEFT JOIN sys.default_constraints dc
                      ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
                    WHERE c.object_id = OBJECT_ID(?)
                    ORDER BY c.column_id
                    """,
                    f"{schema}.{table}",
                )
                cols = cur.fetchall()
                col_defs = []
                for (
                    cname,
                    type_name,
                    max_length,
                    precision,
                    scale,
                    is_nullable,
                    is_identity,
                    default_def,
                ) in cols:
                    type_name = type_name.lower()
                    if type_name in ("nvarchar", "varchar", "varbinary", "nchar", "char"):
                        if max_length == -1:
                            type_sql = f"{type_name}(max)"
                        elif type_name.startswith("n"):
                            type_sql = f"{type_name}({max_length // 2})"
                        else:
                            type_sql = f"{type_name}({max_length})"
                    elif type_name in ("decimal", "numeric"):
                        type_sql = f"{type_name}({precision},{scale})"
                    elif type_name in ("datetime2", "time", "datetimeoffset"):
                        type_sql = f"{type_name}({scale})"
                    else:
                        type_sql = type_name
                    identity = " IDENTITY(1,1)" if is_identity else ""
                    nullability = " NULL" if is_nullable else " NOT NULL"
                    default = f" DEFAULT {default_def}" if default_def else ""
                    col_defs.append(
                        f"    [{cname}] {type_sql}{identity}{nullability}{default}"
                    )
                # PK
                cur.execute(
                    """
                    SELECT c.name
                    FROM sys.indexes i
                    JOIN sys.index_columns ic
                      ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                    JOIN sys.columns c
                      ON c.object_id = ic.object_id AND c.column_id = ic.column_id
                    WHERE i.object_id = OBJECT_ID(?) AND i.is_primary_key = 1
                    ORDER BY ic.key_ordinal
                    """,
                    f"{schema}.{table}",
                )
                pk_cols = [r[0] for r in cur.fetchall()]
                pk_sql = ""
                if pk_cols:
                    pk_list = ", ".join(f"[{c}]" for c in pk_cols)
                    pk_sql = f",\n    CONSTRAINT [PK_{schema}_{table}] PRIMARY KEY ({pk_list})"
                create = (
                    f"IF OBJECT_ID(N'{schema}.{table}', N'U') IS NULL\n"
                    f"BEGIN\n"
                    f"  CREATE TABLE [{schema}].[{table}] (\n"
                    + ",\n".join(col_defs)
                    + pk_sql
                    + "\n  );\n"
                    f"END\n"
                    f"GO\n"
                )
                parts.append(create)
            out[schema] = "\n".join(parts)
    finally:
        cn.close()
    return out


def write_outputs(
    buckets: Dict[str, Dict[str, List[str]]],
    live_extras: Optional[Dict[str, str]] = None,
) -> None:
    mapping = {
        "Meta": ("meta_schema.sql", "meta_api.sql"),
        "RBAC": ("rbac_schema.sql", "rbac_api.sql"),
        "portal": ("portal_clinical_schema.sql", "portal_clinical_api.sql"),
        "Contract": ("contract_schema.sql", "contract_api.sql"),
        "Onboarding": ("onboarding_schema.sql", "onboarding_api.sql"),
    }
    header = (
        "-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql\n"
        "-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).\n"
        "-- Do not edit by hand unless also updating the twin under sql_pg/.\n\n"
    )
    # Portal tables present in monolith — live overlay only adds missing extras.
    PORTAL_LIVE_ONLY = {
        "DiseaseDataSource",
        "DiseaseFieldContract",
        "SampleImportBatch",
        "SampleImportRow",
        "project",
    }
    for schema, (schema_file, api_file) in mapping.items():
        ddl_parts = buckets[schema]["schema_ddl"]
        if schema == "portal" and live_extras and "portal" in live_extras:
            # Keep monolith clinical DDL; append only extra live tables.
            extra_only = []
            for block in live_extras["portal"].split("GO\n"):
                m = re.search(r"CREATE TABLE \[portal\]\.\[(\w+)\]", block)
                if m and m.group(1) in PORTAL_LIVE_ONLY:
                    extra_only.append(block.strip() + "\nGO\n")
            schema_body = header + "\n".join(ddl_parts) + "\n" + "\n".join(extra_only)
        else:
            schema_body = header + "\n".join(ddl_parts)
        (OUT_DIR / schema_file).write_text(schema_body + "\n", encoding="utf-8")
        api_body = header + "\n".join(buckets[schema]["api"])
        (OUT_DIR / api_file).write_text(api_body + "\n", encoding="utf-8")
        print(
            f"Wrote {schema_file} ({len(buckets[schema]['schema_ddl'])} ddl batches) "
            f"and {api_file} ({len(buckets[schema]['api'])} routines)"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-live",
        action="store_true",
        help="Also script table DDL from live Azure SQL (DiseaseFieldContract and other extras).",
    )
    args = parser.parse_args()
    if not MONOLITH.is_file():
        print(f"Missing {MONOLITH}", file=sys.stderr)
        return 1
    buckets = extract_from_monolith()
    live: Optional[Dict[str, str]] = None
    if args.from_live:
        live = script_live_tables(["portal"])
    write_outputs(buckets, live)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
