#!/usr/bin/env python3
"""Push repo pipeline profiles, assay procedures, analytes + action catalog into DB(s).

Use after breaking config/schema changes so ``cfg.pipeline_profile``,
``cfg.assay_procedure``, ``cfg.analyte``, and ``wf.workflow_action`` / schemas
match git.

Profiles/procedures/analytes carry a ``catalog`` block; sync maps that to cfg
``status`` (``published`` vs ``retired``). Research mode overlays under
``profiles/modes/`` are **not** upserted as pipeline_profile rows.

Examples::

  source .venv/bin/activate

  # Azure SQL (AZURE_SQL_* or DB_* from mssql-mcp env)
  export BACKEND_DB=mssql
  python scripts/sync_cfg_profiles_and_action_catalog.py --backend mssql

  # PostgreSQL (POSTGRES_* ; AAD users must URL-encode @ as %40)
  export BACKEND_DB=postgres
  python scripts/sync_cfg_profiles_and_action_catalog.py --backend postgres

Verification (default on):
  - staged profiles lack removed key ``stability_min_selected_dmps``
  - staged profiles contain ``stability_min_core_dmps``
  - ``validation.biomarker_filter`` output schema contains ``empty_reason``
  - deprecated profiles are ``retired``; ``mode_*`` rows are absent
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "workers"), str(REPO / "workflow_engine")]

from cfg.process_pack_catalog import cfg_status_for_catalog  # noqa: E402

# Profiles known to have carried the removed MC key before the effective-config cut.
_DEFAULT_VERIFY_PROFILES = ("staged_ovr_mc", "staged_full_lifecycle")
_REMOVED_KEY = "stability_min_selected_dmps"
_CANONICAL_KEY = "stability_min_core_dmps"

# Legacy mode_* names previously synced as pipeline_profile rows — retire on sync.
_LEGACY_MODE_PROFILE_PREFIX = "mode_"


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


def _profile_items() -> List[Tuple[str, str, Path, Dict[str, Any]]]:
    """Return (name, version, path, doc) for *.profile.json only (no modes)."""
    profiles_dir = REPO / "workflow_engine" / "domain" / "profiles"
    items: List[Tuple[str, str, Path, Dict[str, Any]]] = []
    for path in sorted(profiles_dir.glob("*.profile.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        name = str(doc.get("pipelineProfile") or path.name.replace(".profile.json", ""))
        items.append((name, "1", path, doc))
    return items


def _procedure_items() -> List[Tuple[str, str, Path, Dict[str, Any]]]:
    procedures_dir = (
        REPO / "workflow_engine" / "domain" / "profiles" / "procedures"
    )
    items: List[Tuple[str, str, Path, Dict[str, Any]]] = []
    if not procedures_dir.is_dir():
        return items
    for path in sorted(procedures_dir.glob("*.procedure.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        name = str(
            doc.get("pipelineProcedure") or path.name.replace(".procedure.json", "")
        )
        items.append((name, "1", path, doc))
    return items


def _analyte_items() -> List[Tuple[str, str, Path, Dict[str, Any]]]:
    analytes_dir = REPO / "workflow_engine" / "domain" / "analytes"
    items: List[Tuple[str, str, Path, Dict[str, Any]]] = []
    if not analytes_dir.is_dir():
        return items
    for path in sorted(analytes_dir.glob("*.analyte.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        name = str(doc.get("name") or path.name.replace(".analyte.json", ""))
        version = str(doc.get("version") or "1")
        items.append((name, version, path, doc))
    return items


def _upsert_kind(
    db,
    *,
    kind: str,
    name: str,
    version: str,
    status: str,
    doc: Dict[str, Any],
) -> None:
    backend = os.environ.get("BACKEND_DB", "mssql").lower()
    payload = json.dumps(doc, separators=(",", ":"))
    if backend == "postgres":
        db._exec_proc(  # noqa: SLF001
            "SELECT * FROM cfg.cfg_repo_upsert(%s, %s, %s, %s, %s::jsonb)",
            (kind, name, version, status, payload),
        )
    else:
        db._exec_proc(  # noqa: SLF001
            "EXEC cfg.cfg_repo_upsert @kind=?, @name=?, @version=?, @status=?, @document_json=?",
            (kind, name, version, status, payload),
        )


def upsert_profiles(
    db,
    *,
    names: Optional[Sequence[str]] = None,
) -> List[str]:
    updated: List[str] = []
    for name, version, _path, doc in _profile_items():
        if names is not None and name not in names:
            continue
        status = cfg_status_for_catalog(doc.get("catalog"))
        if status is None:
            print(f"skip pipeline_profile:{name} (catalog says omit)")
            continue
        _upsert_kind(
            db, kind="pipeline_profile", name=name, version=version, status=status, doc=doc
        )
        updated.append(f"{name}@{version}:{status}")
        print(f"upserted pipeline_profile:{name}@{version} status={status}")
    return updated


def _program_name_from_path(path_or_name: object) -> Optional[str]:
    """Resolve DomainProgram cfg name from a fixture path or bare name."""
    if path_or_name is None:
        return None
    raw = str(path_or_name).strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        candidate = REPO / path
    else:
        candidate = path
    if candidate.is_file():
        try:
            doc = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = {}
        name = doc.get("name")
        if name:
            return str(name)
    # Fall back to fixture stem (sample_prep.program.json → sample_prep)
    stem = path.name
    if stem.endswith(".program.json"):
        stem = stem[: -len(".program.json")]
    return stem or None


def _analyte_token(doc: Dict[str, Any]) -> Optional[str]:
    exp = doc.get("analyteExpectation")
    if isinstance(exp, str) and exp.strip():
        return exp.strip().lower()
    if isinstance(exp, list) and exp:
        return str(exp[0]).strip().lower() or None
    return None


def upsert_analytes(
    db,
    *,
    names: Optional[Sequence[str]] = None,
) -> List[str]:
    updated: List[str] = []
    for name, version, _path, doc in _analyte_items():
        if names is not None and name not in names:
            continue
        status = cfg_status_for_catalog(doc.get("catalog"))
        if status is None:
            print(f"skip analyte:{name} (catalog says omit)")
            continue
        _upsert_kind(
            db, kind="analyte", name=name, version=version, status=status, doc=doc
        )
        updated.append(f"{name}@{version}:{status}")
        print(f"upserted analyte:{name}@{version} status={status}")
    return updated


def upsert_procedures(
    db,
    *,
    names: Optional[Sequence[str]] = None,
) -> List[str]:
    updated: List[str] = []
    for name, version, _path, doc in _procedure_items():
        if names is not None and name not in names:
            continue
        status = cfg_status_for_catalog(doc.get("catalog"))
        if status is None:
            print(f"skip assay_procedure:{name} (catalog says omit)")
            continue
        _upsert_kind(
            db, kind="assay_procedure", name=name, version=version, status=status, doc=doc
        )
        updated.append(f"{name}@{version}:{status}")
        print(f"upserted assay_procedure:{name}@{version} status={status}")
        bind_assay_procedure(db, name=name, version=version, doc=doc)
    return updated


def backfill_study_analyte_defaults(db) -> None:
    """Bind study.default_analyte_id from regulatory.primary_analyte when unset."""
    backend = os.environ.get("BACKEND_DB", "mssql").lower()
    try:
        if backend == "postgres":
            rows = db._fetch_all(  # noqa: SLF001
                "SELECT * FROM cfg.cfg_repo_backfill_study_analyte_defaults()",
                (),
            )
        else:
            rows = db._fetch_all(  # noqa: SLF001
                "EXEC cfg.cfg_repo_backfill_study_analyte_defaults",
                (),
            )
        n = (rows[0] or {}).get("studies_updated") if rows else 0
        print(f"backfilled study default_analyte_id rows={n}")
    except Exception as exc:  # noqa: BLE001 — links may be undeployed
        print(f"warn: study analyte backfill failed: {exc}")


def bind_assay_procedure(
    db,
    *,
    name: str,
    version: str,
    doc: Dict[str, Any],
) -> None:
    """Set typed FKs on cfg.assay_procedure via cfg.cfg_repo_bind_assay_procedure."""
    backend = os.environ.get("BACKEND_DB", "mssql").lower()
    analyte = _analyte_token(doc)
    profile = doc.get("pipelineProfile")
    profile_name = str(profile).strip() if profile else None
    sp_name = _program_name_from_path(doc.get("samplePrepProgram"))
    lc_name = _program_name_from_path(doc.get("lifecycleProgram"))
    try:
        if backend == "postgres":
            db._exec_proc(  # noqa: SLF001
                "SELECT * FROM cfg.cfg_repo_bind_assay_procedure(%s, %s, %s, %s, %s, %s)",
                (name, version, analyte, profile_name, sp_name, lc_name),
            )
        else:
            db._exec_proc(  # noqa: SLF001
                "EXEC cfg.cfg_repo_bind_assay_procedure "
                "@procedure_name=?, @procedure_version=?, @primary_analyte=?, "
                "@default_pipeline_profile_name=?, @sample_prep_program_name=?, "
                "@lifecycle_program_name=?",
                (name, version, analyte, profile_name, sp_name, lc_name),
            )
        print(
            f"bound assay_procedure:{name} analyte={analyte} "
            f"profile={profile_name} samplePrep={sp_name} lifecycle={lc_name}"
        )
    except Exception as exc:  # noqa: BLE001 — sync continues; links may be undeployed
        print(f"warn: bind assay_procedure:{name} failed: {exc}")


def retire_legacy_mode_profiles(db) -> int:
    """Mark leftover mode_* pipeline_profile rows retired (no longer synced)."""
    backend = os.environ.get("BACKEND_DB", "mssql").lower()
    if backend == "postgres":
        rows = db._fetch_all(  # noqa: SLF001
            """
            UPDATE cfg.pipeline_profile
            SET status = 'retired', updated_at_utc = (now() AT TIME ZONE 'utc')
            WHERE name LIKE %s AND status <> 'retired'
            RETURNING name
            """,
            (f"{_LEGACY_MODE_PROFILE_PREFIX}%",),
        )
    else:
        rows = db._fetch_all(  # noqa: SLF001
            """
            UPDATE cfg.pipeline_profile
            SET status = 'retired', updated_at_utc = SYSUTCDATETIME()
            OUTPUT inserted.name
            WHERE name LIKE ? AND status <> 'retired'
            """,
            (f"{_LEGACY_MODE_PROFILE_PREFIX}%",),
        )
    for row in rows or []:
        print("retired legacy mode profile", row.get("name"))
    return len(rows or [])


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
            SELECT name, status,
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
            SELECT name, status,
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


def verify_catalog_status(db) -> None:
    """Ensure deprecated profiles are retired and mode_* rows are not published."""
    backend = os.environ.get("BACKEND_DB", "mssql").lower()
    if backend == "postgres":
        rows = db._fetch_all(  # noqa: SLF001
            """
            SELECT name, status,
                   document_json->'catalog'->>'lifecycle' AS lifecycle,
                   document_json->'catalog'->>'visibility' AS visibility
            FROM cfg.pipeline_profile
            WHERE name LIKE 'mc_%'
               OR name IN ('legacy_dual', 'discovery_gene_featurecuts',
                           'dmp_panel_stability', 'gene_enricher_stability')
               OR name LIKE 'mode_%'
            ORDER BY name
            """,
            (),
        )
    else:
        rows = db._fetch_all(  # noqa: SLF001
            """
            SELECT name, status,
                   JSON_VALUE(CAST(document_json AS nvarchar(max)), '$.catalog.lifecycle') AS lifecycle,
                   JSON_VALUE(CAST(document_json AS nvarchar(max)), '$.catalog.visibility') AS visibility
            FROM cfg.pipeline_profile
            WHERE name LIKE 'mc_%'
               OR name IN (N'legacy_dual', N'discovery_gene_featurecuts',
                           N'dmp_panel_stability', N'gene_enricher_stability')
               OR name LIKE 'mode_%'
            ORDER BY name
            """,
            (),
        )
    published_bad = [
        r
        for r in (rows or [])
        if str(r.get("status") or "").lower() == "published"
        and (
            str(r.get("name") or "").startswith(_LEGACY_MODE_PROFILE_PREFIX)
            or str(r.get("lifecycle") or "").lower() == "deprecated"
            or str(r.get("visibility") or "").lower() == "hidden"
        )
    ]
    for row in rows or []:
        print("verify catalog status", row)
    if published_bad:
        raise SystemExit(
            "deprecated/mode profiles still published (expected retired): "
            f"{published_bad}"
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
            upsert_analytes(db)
            upsert_profiles(db, names=profiles)
            upsert_procedures(db)
            backfill_study_analyte_defaults(db)
            retire_legacy_mode_profiles(db)
            if not skip_verify:
                verify_names = (
                    list(profiles)
                    if profiles is not None
                    else list(_DEFAULT_VERIFY_PROFILES)
                )
                verify_profiles(db, verify_names)
                verify_catalog_status(db)
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
        description=(
            "Sync repo pipeline profiles, assay procedures + action catalog "
            "into gateway DB(s)."
        )
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
