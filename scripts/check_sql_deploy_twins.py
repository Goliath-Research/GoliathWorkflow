#!/usr/bin/env python3
"""Fail if sql_mssql/deploy_azure.sh and sql_pg/deploy_azure.sh drift.

Same-basename SQL files that exist in both trees and are listed in either
deploy_azure.sh SCRIPTS array must be listed in both. Duplicates in a list
are errors. Missing files on disk are errors.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MSSQL_DEPLOY = REPO / "workflow_engine" / "sql_mssql" / "deploy_azure.sh"
PG_DEPLOY = REPO / "workflow_engine" / "sql_pg" / "deploy_azure.sh"
MSSQL_DIR = REPO / "workflow_engine" / "sql_mssql"
PG_DIR = REPO / "workflow_engine" / "sql_pg"


def parse_scripts_array(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    marker = "SCRIPTS=("
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"No SCRIPTS=( array in {path}")
    names: list[str] = []
    for line in text[start + len(marker) :].splitlines():
        stripped = line.strip()
        if stripped.startswith(")"):
            break
        if not stripped or stripped.startswith("#"):
            continue
        token = stripped.split("#", 1)[0].strip().rstrip("\\").strip()
        if token:
            names.append(token)
    if not names:
        raise ValueError(f"Empty SCRIPTS array in {path}")
    return names


def main() -> int:
    exit_code = 0
    mssql_list = parse_scripts_array(MSSQL_DEPLOY)
    pg_list = parse_scripts_array(PG_DEPLOY)

    for label, names, directory in (
        ("mssql", mssql_list, MSSQL_DIR),
        ("postgres", pg_list, PG_DIR),
    ):
        seen: set[str] = set()
        dups: list[str] = []
        for n in names:
            if n in seen:
                dups.append(n)
            seen.add(n)
        if dups:
            print(f"[{label}] duplicate entries in deploy_azure.sh: {dups}", file=sys.stderr)
            exit_code = 1
        for n in names:
            if not (directory / n).is_file():
                print(f"[{label}] listed but missing on disk: {n}", file=sys.stderr)
                exit_code = 1

    mssql_set = set(mssql_list)
    pg_set = set(pg_list)
    mssql_files = {p.name for p in MSSQL_DIR.glob("*.sql")}
    pg_files = {p.name for p in PG_DIR.glob("*.sql")}
    shared_on_disk = mssql_files & pg_files
    listed_either = mssql_set | pg_set
    for name in sorted(shared_on_disk & listed_either):
        missing_mssql = name not in mssql_set
        missing_pg = name not in pg_set
        if missing_mssql or missing_pg:
            side = "mssql" if missing_mssql else "postgres"
            print(
                f"[twins] {name} exists in both sql trees and is listed in one "
                f"deploy_azure.sh but not {side}",
                file=sys.stderr,
            )
            exit_code = 1

    if exit_code == 0:
        print(
            f"SQL deploy twins OK ({len(mssql_set)} mssql, {len(pg_set)} postgres, "
            f"{len(shared_on_disk & listed_either)} shared listed basenames)"
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
