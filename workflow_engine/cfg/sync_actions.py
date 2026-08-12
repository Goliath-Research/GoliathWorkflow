"""Sync action catalog into wf (workflow_action + data_type). cfg.action_definition retired."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

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
    """Deprecated cfg path — actions live in wf. Prefer seed_wf_from_catalog."""
    del store, publish
    return seed_wf_from_catalog(repo_root=repo_root)


def sync_actions_from_committed_json(
    store: ConfigStore,
    *,
    repo_root: Path | str,
    publish: bool = True,
) -> Dict[str, Any]:
    """Deprecated cfg path — actions live in wf. Prefer seed_wf_from_catalog."""
    del store, publish
    return seed_wf_from_catalog(repo_root=repo_root)


def seed_wf_from_catalog(
    *,
    repo_root: Path | str,
    use_db: bool = True,
) -> Dict[str, Any]:
    """Seed wf.workflow_action + wf.data_type via seed_action_catalog.py."""
    repo_root = Path(repo_root)
    _ensure_paths(repo_root)
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
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "direction": "catalog_to_wf",
    }
