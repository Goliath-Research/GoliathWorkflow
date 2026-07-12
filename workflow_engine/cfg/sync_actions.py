"""Sync action definitions between client catalog, cfg store, and optional wf seed."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .store import ConfigStore


def _ensure_paths(repo_root: Path) -> None:
    for p in (
        str(repo_root),
        str(repo_root / "workflow_engine"),
        str(repo_root / "workers"),
    ):
        if p not in sys.path:
            sys.path.insert(0, p)


def sync_actions_from_catalog(
    store: ConfigStore,
    *,
    repo_root: Path | str,
    publish: bool = True,
) -> Dict[str, Any]:
    """Client → cfg: upsert each ACTION_CATALOG entry as action_definition."""
    repo_root = Path(repo_root)
    _ensure_paths(repo_root)
    from methyl_worker.action_catalog import ACTION_CATALOG

    status = "published" if publish else "draft"
    names: List[str] = []
    for entry in ACTION_CATALOG:
        if hasattr(entry, "model_dump"):
            doc = entry.model_dump(mode="json")
        elif isinstance(entry, dict):
            doc = entry
        else:
            doc = dict(entry.__dict__)
        name = str(doc.get("action_name") or doc.get("name"))
        store.upsert(
            "action_definition",
            name,
            doc,
            status=status,
            extra={"implementationStatus": "present"},
        )
        # Keep implementation_status on document too for materialize consumers
        doc = {**doc, "implementationStatus": "present"}
        store.upsert("action_definition", name, doc, status=status)
        names.append(name)
    return {"synced": names, "count": len(names), "direction": "catalog_to_cfg"}


def sync_actions_from_committed_json(
    store: ConfigStore,
    *,
    repo_root: Path | str,
    publish: bool = True,
) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    catalog_path = repo_root / "schemas" / "actions" / "catalog.json"
    if not catalog_path.is_file():
        return sync_actions_from_catalog(store, repo_root=repo_root, publish=publish)
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries = raw if isinstance(raw, list) else raw.get("actions") or raw.get("entries") or []
    status = "published" if publish else "draft"
    names: List[str] = []
    for doc in entries:
        name = str(doc.get("action_name") or doc.get("name"))
        store.upsert(
            "action_definition",
            name,
            {**doc, "implementationStatus": "present"},
            status=status,
        )
        names.append(name)
    return {"synced": names, "count": len(names), "direction": "json_to_cfg"}


def seed_wf_from_catalog(
    *,
    repo_root: Path | str,
    use_db: bool = True,
) -> Dict[str, Any]:
    """Delegate to existing seed_action_catalog.py (client → wf)."""
    repo_root = Path(repo_root)
    script = repo_root / "workflow_engine" / "sql_mssql" / "seed_action_catalog.py"
    if not script.is_file():
        raise FileNotFoundError(script)
    import subprocess

    cmd = [sys.executable, str(script)]
    if use_db:
        cmd.append("--use-db")
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }
