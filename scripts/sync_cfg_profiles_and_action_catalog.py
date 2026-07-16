#!/usr/bin/env python3
"""Push repo pipeline profiles + action catalog into Azure SQL and/or PostgreSQL.

Use after breaking config/schema changes so ``cfg.pipeline_profile`` and
``wf.workflow_action`` / ``wf.workflow_action_schema`` match git.

Examples::

  source .venv/bin/activate

  # Azure SQL (AZURE_SQL_* or DB_* from mssql-mcp env)
  export BACKEND_DB=mssql
  python scripts/sync_cfg_profiles_and_action_catalog.py --backend mssql

  # PostgreSQL (POSTGRES_* ; AAD users must URL-encode @ as %40)
  export BACKEND_DB=postgres
  export POSTGRES_HOST=... POSTGRES_DB=... POSTGRES_USER=... POSTGRES_PASSWORD=...
  python scripts/sync_cfg_profiles_and_action_catalog.py --backend postgres

  # Both sequentially (each backend uses its own env; set credentials before each run)
  python scripts/sync_cfg_profiles_and_action_catalog.py --backend both

Verification (default on):
  - staged profiles lack removed key ``stability_min_selected_dmps``
  - staged profiles contain ``stability_min_core_dmps``
  - ``validation.biomarker_filter`` output schema contains ``empty_reason``
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "workers"), str(REPO / "workflow_engine")]

# Profiles known to have carried the removed MC key before the effective-config cut.
_DEFAULT_VERIFY_PROFILES = ("staged_ovr_mc", "staged_full_lifecycle")
_REMOVED_KEY = "stability_min_selected_dmps"
_CANONICAL_KEY = "stability_min_core_dmps"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _prepare_mssql_env() -> None:
    # Optional local helper files (never committed secrets).
    _load_dotenv(Path.home() / "mssql-mcp-server" / ".env")
    _load_dotenv(Path.home() / ".secrets" / "azure_sql.env")
    os.environ["BACKEND_DB"] = "mssql"
    if os.environ.get("DB_SERVER") and not os.environ.get("AZURE_SQL_SERVER"):
        os.environ["AZURE_SQL_SERVER"] = os.environ["DB_SERVER"]
    if os.environ.get("DB_DATABASE") and not os.environ.get("AZURE_SQL_DB"):
        os.environ["AZURE_SQL_DB"] = os.environ["DB_DATABASE"]
    if os.environ.get("DB_USER") and not os.environ.get("AZURE_SQL_USER"):
        os.environ["AZURE_SQL_USER"] = os.environ["DB_USER"]
    if os.environ.get("DB_PASSWORD") and not os.environ.get("AZURE_SQL_PASSWORD"):
        os.environ["AZURE_SQL_PASSWORD"] = os.environ["DB_PASSWORD"]


def _prepare_postgres_env() -> None:
    os.environ["BACKEND_DB"] = "postgres"


def _open_db():
    from rest.connection import resolve_connection_config
    from rest.db import open_gateway_db

    return open_gateway_db(resolve_connection_config())


def _profile_items() -> List[tuple[str, str, Path]]:
    profiles_dir = REPO / "workflow_engine" / "domain" / "profiles"
    items: List[tuple[str, str, Path]] = []
    for path in sorted(profiles_dir.glob("*.profile.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        name = str(doc.get("pipelineProfile") or path.name.replace(".profile.json", ""))
        items.append((name, "1", path))
    modes = profiles_dir / "modes"
    if modes.is_dir():
        for path in sorted(modes.glob("*.mode.json")):
            name = f"mode_{path.name.replace('.mode.json', '')}"
            items.append((name, "mode", path))
    return items


def upsert_profiles(
    db,
    *,
    names: Optional[Sequence[str]] = None,
) -> List[str]:
    backend = os.environ.get("BACKEND_DB", "mssql").lower()
    updated: List[str] = []
    for name, version, path in _profile_items():
        if names is not None and name not in names:
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        payload = json.dumps(doc, separators=(",", ":"))
        if backend == "postgres":
            db._exec_proc(  # noqa: SLF001 — admin sync via cfg_repo_upsert
                "SELECT * FROM cfg.cfg_repo_upsert(%s, %s, %s, %s, %s::jsonb)",
                ("pipeline_profile", name, version, "published", payload),
            )
        else:
            db._exec_proc(  # noqa: SLF001
                "EXEC cfg.cfg_repo_upsert @kind=?, @name=?, @version=?, @status=?, @document_json=?",
                ("pipeline_profile", name, version, "published", payload),
            )
        updated.append(f"{name}@{version}")
        print(f"upserted pipeline_profile:{name}@{version}")
    return updated


def seed_action_catalog() -> None:
    script = REPO / "workflow_engine" / "sql_mssql" / "seed_action_catalog.py"
    cmd = [sys.executable, str(script), "--regenerate-catalog", "--use-db"]
    print("running", " ".join(cmd), "BACKEND_DB=", os.environ.get("BACKEND_DB"))
    subprocess.run(cmd, check=True, cwd=str(REPO), env=os.environ.copy())


def verify_profiles(db, names: Iterable[str]) -> None:
    names_list = list(names)
    if not names_list:
        raise SystemExit("verify_profiles: no profile names requested")

    backend = os.environ.get("BACKEND_DB", "mssql").lower()
    if backend == "postgres":
        rows = db._fetch_all(  # noqa: SLF001
            """
            SELECT name,
                   (document_json::text LIKE %s) AS has_removed,
                   (document_json::text LIKE %s) AS has_canonical
            FROM cfg.pipeline_profile
            WHERE name = ANY(%s)
            ORDER BY name
            """,
            (f"%{_REMOVED_KEY}%", f"%{_CANONICAL_KEY}%", names_list),
        )
    else:
        placeholders = ",".join("?" for _ in names_list)
        rows = db._fetch_all(  # noqa: SLF001
            f"""
            SELECT name,
                   CASE WHEN CAST(document_json AS nvarchar(max)) LIKE ? THEN 1 ELSE 0 END AS has_removed,
                   CASE WHEN CAST(document_json AS nvarchar(max)) LIKE ? THEN 1 ELSE 0 END AS has_canonical
            FROM cfg.pipeline_profile
            WHERE name IN ({placeholders})
            ORDER BY name
            """,
            (f"%{_REMOVED_KEY}%", f"%{_CANONICAL_KEY}%", *names_list),
        )

    found = {str(r.get("name")) for r in rows if r.get("name") is not None}
    expected = set(names_list)
    absent = sorted(expected - found)
    if absent:
        raise SystemExit(
            "verify_profiles: expected profile(s) missing from cfg.pipeline_profile: "
            f"{absent} (got {sorted(found) if found else 'no rows'})"
        )

    for row in rows:
        print("verify profile", row)
    bad = [r for r in rows if r.get("has_removed") in (True, 1)]
    if bad:
        raise SystemExit(f"removed key {_REMOVED_KEY!r} still present: {bad}")
    missing_canonical = [r for r in rows if r.get("has_canonical") not in (True, 1)]
    if missing_canonical:
        raise SystemExit(
            f"canonical key {_CANONICAL_KEY!r} missing: {missing_canonical}"
        )


def verify_biomarker_schema(db) -> None:
    backend = os.environ.get("BACKEND_DB", "mssql").lower()
    if backend == "postgres":
        rows = db._fetch_all(  # noqa: SLF001
            """
            SELECT a.action_name, s.direction,
                   (s.schema_json::text LIKE %s) AS has_empty_reason
            FROM wf.workflow_action_schema s
            JOIN wf.workflow_action a ON a.id = s.workflow_action_id
            WHERE a.action_name = %s AND s.direction = %s
            """,
            ("%empty_reason%", "validation.biomarker_filter", "output"),
        )
    else:
        rows = db._fetch_all(  # noqa: SLF001
            """
            SELECT a.action_name, s.direction,
                   CASE WHEN CAST(s.schema_json AS nvarchar(max)) LIKE ? THEN 1 ELSE 0 END AS has_empty_reason
            FROM wf.workflow_action_schema s
            JOIN wf.workflow_action a ON a.id = s.workflow_action_id
            WHERE a.action_name = ? AND s.direction = ?
            """,
            ("%empty_reason%", "validation.biomarker_filter", "output"),
        )
    row = rows[0] if rows else None
    print("verify biomarker schema", row)
    if not row or row.get("has_empty_reason") not in (True, 1):
        raise SystemExit(
            "validation.biomarker_filter output schema missing empty_reason "
            "(re-run seed / methyl-export-task-schemas)"
        )


def run_backend(
    backend: str,
    *,
    profiles: Optional[Sequence[str]],
    skip_profiles: bool,
    skip_seed: bool,
    skip_verify: bool,
) -> None:
    if backend == "mssql":
        _prepare_mssql_env()
    else:
        _prepare_postgres_env()

    print(
        f"==> backend={backend} "
        f"mssql={os.environ.get('AZURE_SQL_SERVER')} "
        f"pg={os.environ.get('POSTGRES_HOST')}"
    )

    if not skip_profiles:
        db = _open_db()
        try:
            upsert_profiles(db, names=profiles)
            if not skip_verify:
                verify_names = (
                    list(profiles)
                    if profiles is not None
                    else list(_DEFAULT_VERIFY_PROFILES)
                )
                verify_profiles(db, verify_names)
        finally:
            db.close()

    if not skip_seed:
        seed_action_catalog()
        if not skip_verify:
            db = _open_db()
            try:
                verify_biomarker_schema(db)
            finally:
                db.close()

    print(f"==> {backend} sync complete")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync repo pipeline profiles + action catalog into gateway DB(s)."
    )
    parser.add_argument(
        "--backend",
        choices=("mssql", "postgres", "both"),
        required=True,
        help="Target database backend (both = mssql then postgres; set env per backend).",
    )
    parser.add_argument(
        "--profiles",
        default="all",
        help="Comma-separated profile names, or 'all' (default).",
    )
    parser.add_argument("--skip-profiles", action="store_true")
    parser.add_argument("--skip-seed", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args(argv)

    profile_names: Optional[List[str]]
    if args.profiles.strip() == "all":
        profile_names = None
    else:
        profile_names = [n.strip() for n in args.profiles.split(",") if n.strip()]

    backends = ("mssql", "postgres") if args.backend == "both" else (args.backend,)
    for backend in backends:
        run_backend(
            backend,
            profiles=profile_names,
            skip_profiles=args.skip_profiles,
            skip_seed=args.skip_seed,
            skip_verify=args.skip_verify,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
