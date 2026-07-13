"""Mandatory cfg → /work sync before a study run starts."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .store import FileConfigStore
from .study_membership import materialize_study_membership

logger = logging.getLogger(__name__)


def resolve_work_root(context: Mapping[str, Any] | None = None) -> Path:
    ctx = context or {}
    raw = (
        ctx.get("workRoot")
        or ctx.get("work_root")
        or os.environ.get("METHYL_WORK_ROOT")
        or "/work"
    )
    return Path(str(raw))


def resolve_cfg_store_dir() -> Optional[Path]:
    env = os.environ.get("METHYL_CFG_STORE")
    if env:
        return Path(env)
    work = Path(os.environ.get("METHYL_WORK_ROOT", "/work"))
    candidate = work / "epimethyl" / "cfg-store"
    if candidate.is_dir():
        return candidate
    return None


def resolve_study_name(context: Mapping[str, Any]) -> Optional[str]:
    for key in ("cfgStudyName", "studyName", "study"):
        val = context.get(key)
        if val not in (None, ""):
            return str(val)
    project = context.get("project")
    if isinstance(project, dict):
        for key in ("project_name", "projectName", "name"):
            val = project.get(key)
            if val not in (None, ""):
                return str(val)
    project_path = context.get("projectPath") or context.get("project_path")
    if project_path:
        stem = Path(str(project_path)).stem
        if stem.startswith("project_"):
            return stem[len("project_") :]
        return stem
    return None


def resolve_study_row_id(context: Mapping[str, Any]) -> Optional[int]:
    for key in ("cfgStudyRowId", "studyRowId", "study_row_id"):
        val = context.get(key)
        if val is not None and str(val).strip() != "":
            return int(val)
    return None


def _write_csv_from_keys(path: Path, sample_keys: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    if sample_keys:
        keys = [k.strip() for k in str(sample_keys).splitlines() if k.strip()]
    lines = ["sample"] + sorted(keys)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _sync_from_db(
    db: Any,
    *,
    study_row_id: int,
    work_root: Path,
) -> Dict[str, Any]:
    """Call cfg_repo_materialize_study_lists and write returned CSV paths."""
    written: list[str] = []
    rows: list[Any] = []
    # Backend-agnostic: prefer a helper if present, else raw SQL shapes.
    if hasattr(db, "cfg_materialize_study_lists"):
        rows = list(db.cfg_materialize_study_lists(study_row_id, str(work_root)))
    elif hasattr(db, "execute"):
        # Best-effort dialect-agnostic call sites use named helpers elsewhere.
        raise RuntimeError(
            "db adapter missing cfg_materialize_study_lists; "
            "use FileConfigStore sync or extend the gateway DB client"
        )
    else:
        raise RuntimeError("unsupported db object for study work sync")

    for row in rows:
        if isinstance(row, Mapping):
            csv_path = row.get("csv_path") or row.get("csvPath")
            sample_keys = row.get("sample_keys") or row.get("sampleKeys")
        else:
            # tuple-like: study_group_id, role, label, list_filename, csv_path, sample_keys
            csv_path = row[4] if len(row) > 4 else None
            sample_keys = row[5] if len(row) > 5 else None
        if csv_path:
            _write_csv_from_keys(Path(str(csv_path)), sample_keys)
            written.append(str(csv_path))
    return {"source": "db", "studyRowId": study_row_id, "written": written}


def ensure_study_work_synced(
    context: Mapping[str, Any] | Dict[str, Any],
    *,
    work_root: Path | str | None = None,
    store: Optional[FileConfigStore] = None,
    db: Any = None,
    study_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Synchronize published cfg study membership onto ``/work`` before a run.

    - No-op when there is no cfg store and no ``study_row_id`` (legacy file-only studies).
    - When the study is in the cfg store (with or without ``studyGroups``), rewrite
      project JSON and membership CSVs under the work root.
    - When ``db`` + ``cfgStudyRowId`` are provided, also run DB materialize and write CSVs.
    - Raises on failure when cfg membership exists so runs never start against stale lists.
    """
    out = dict(context)
    if out.get("cfgWorkSynced") and out.get("skipCfgWorkSync"):
        return out
    if out.get("skipCfgWorkSync"):
        out["cfgWorkSynced"] = False
        return out

    root = Path(work_root) if work_root else resolve_work_root(out)
    name = study_name or resolve_study_name(out)
    row_id = resolve_study_row_id(out)
    sync_meta: Dict[str, Any] = {"workRoot": str(root), "studyName": name, "written": []}

    store_obj = store
    if store_obj is None:
        store_dir = resolve_cfg_store_dir()
        if store_dir is not None:
            store_obj = FileConfigStore(store_dir)

    try:
        if store_obj is not None and name:
            # Always refresh published study document + membership CSVs when present.
            rec = store_obj.get("study", name, published_only=True)
            if rec is not None:
                result = materialize_study_membership(
                    store_obj, root, study_name=name
                )
                sync_meta["source"] = "file_store"
                sync_meta["written"].extend(result.get("written") or [])
                # Prefer freshly synced project path for the run when we know studyId.
                study_id = (
                    rec.extra.get("studyId")
                    or rec.document.get("study_id")
                    or rec.document.get("studyId")
                    or rec.name
                )
                synced_project = (
                    root / "projects" / str(study_id) / "configs" / f"project_{rec.name}.json"
                )
                if synced_project.is_file():
                    out["projectPath"] = str(synced_project)
                    # Reload document after membership sync
                    refreshed = store_obj.get("study", name, published_only=True)
                    if refreshed is not None:
                        out.setdefault("project", refreshed.document)

        if db is not None and row_id is not None:
            db_result = _sync_from_db(db, study_row_id=row_id, work_root=root)
            sync_meta["db"] = db_result
            sync_meta["written"].extend(db_result.get("written") or [])

    except Exception as exc:
        logger.error("cfg → /work study sync failed: %s", exc)
        raise RuntimeError(
            f"study work area sync failed before run start ({name or row_id}): {exc}"
        ) from exc

    out["cfgWorkSynced"] = True
    out["cfgWorkSync"] = sync_meta
    logger.info(
        "cfg → /work study sync ok study=%s written=%d",
        name or row_id,
        len(sync_meta["written"]),
    )
    return out
