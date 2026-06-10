#!/usr/bin/env python3
"""Validate DB object contract parity between sql/ (T-SQL) and sql_pg/ (PL/pgSQL)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_YAML = Path(__file__).resolve().parent / "db_objects.yaml"
SQL_DIRS = {
    "mssql": ROOT / "sql",
    "postgres": ROOT / "sql_pg",
}

# Patterns to detect object definitions in deploy scripts
OBJECT_PATTERNS = [
    re.compile(r"CREATE\s+(?:OR\s+ALTER\s+)?PROCEDURE\s+([\w.]+)", re.I),
    re.compile(r"CREATE\s+(?:OR\s+ALTER\s+)?FUNCTION\s+([\w.]+)", re.I),
    re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([\w.]+)", re.I),
    re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+([\w.]+)", re.I),
]

# JSON payload columns must use native json (MSSQL) / jsonb (PG), not NVARCHAR(MAX) or text.
FORBIDDEN_JSON_COL = re.compile(
    r"^\s*(value_json|data_json|context_value_json|config_json|task_config_json)\s+"
    r"(?:nvarchar\s*\(\s*max\s*\)|text)\s",
    re.I | re.M,
)


def load_required_objects() -> list[str]:
    if yaml is None:
        # Minimal fallback if PyYAML not installed
        text = CONTRACT_YAML.read_text(encoding="utf-8")
        names: list[str] = []
        for line in text.splitlines():
            if "name:" in line and "wf." in line:
                m = re.search(r"name:\s*(wf\.[\w.]+|dbo\.\w+)", line)
                if m:
                    names.append(m.group(1).lower())
        return names

    data = yaml.safe_load(CONTRACT_YAML.read_text(encoding="utf-8"))
    names = []
    for section in data.get("objects", {}).values():
        for obj in section:
            if obj.get("required", True):
                names.append(str(obj["name"]).lower())
    return names


def scan_sql_dir(directory: Path) -> set[str]:
    found: set[str] = set()
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.sql")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pat in OBJECT_PATTERNS:
            for m in pat.finditer(text):
                found.add(m.group(1).lower())
    return found


def audit_json_column_types(directories: dict[str, Path]) -> int:
    """Fail if wf_* deploy scripts declare JSON payload columns as NVARCHAR(MAX) or text."""
    exit_code = 0
    for dialect, directory in directories.items():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("wf_*.sql")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in FORBIDDEN_JSON_COL.finditer(text):
                print(
                    f"[{dialect}] forbidden JSON column type in {path.name}: "
                    f"{match.group(0).strip()} (use json/jsonb)",
                    file=sys.stderr,
                )
                exit_code = 1
    return exit_code


def main() -> int:
    required = load_required_objects()
    if not required:
        print("No required objects loaded from contract.", file=sys.stderr)
        return 1

    results: dict[str, set[str]] = {k: scan_sql_dir(v) for k, v in SQL_DIRS.items()}
    exit_code = 0

    for dialect, found in results.items():
        missing = [n for n in required if n not in found and not n.startswith("dbo.")]
        if dialect == "postgres" and missing:
            # dbo objects optional on postgres
            pass
        if missing:
            print(f"[{dialect}] missing {len(missing)} contract object(s):")
            for name in missing:
                print(f"  - {name}")
            exit_code = 1
        else:
            print(f"[{dialect}] all required contract objects present ({len(required)} checked)")

    # Cross-dialect wf.* parity (exclude optional dbo)
    wf_required = [n for n in required if n.startswith("wf.")]
    mssql_wf = {n for n in results["mssql"] if n.startswith("wf.")}
    pg_wf = {n for n in results["postgres"] if n.startswith("wf.")}
    only_mssql = sorted(mssql_wf - pg_wf)
    only_pg = sorted(pg_wf - mssql_wf)
    for name in wf_required:
        if name not in mssql_wf:
            print(f"[mssql] contract requires {name} but not found in sql/")
            exit_code = 1
        if name not in pg_wf:
            print(f"[postgres] contract requires {name} but not found in sql_pg/")
            exit_code = 1

    if only_mssql or only_pg:
        print("\nwf.* object skew (non-contract extras allowed):")
        for n in only_mssql[:20]:
            print(f"  mssql-only: {n}")
        for n in only_pg[:20]:
            print(f"  postgres-only: {n}")

    exit_code |= audit_json_column_types(SQL_DIRS)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
