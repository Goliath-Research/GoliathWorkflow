"""Append-only JSONL audit log for validation / Monte Carlo workflow actions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def action_run_log_path(mc_root: Path) -> Path:
    return Path(mc_root) / "action_run_log.jsonl"


def append_action_run_log(
    mc_root: Path,
    *,
    action: str,
    capability: str,
    result_code: int = 0,
    run_dir: Optional[str] = None,
    inputs: Optional[Dict[str, Any]] = None,
    outputs: Optional[Dict[str, Any]] = None,
    workflow_node_key: Optional[str] = None,
) -> Path:
    """Append one JSON line to {monteCarloRunsRoot}/action_run_log.jsonl."""
    mc_root = Path(mc_root)
    log_path = action_run_log_path(mc_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts_utc": _utc_now_iso(),
        "action": action,
        "capability": capability,
        "result_code": result_code,
        "run_dir": run_dir,
        "inputs": inputs or {},
        "outputs": outputs or {},
        "workflow_node_key": workflow_node_key,
    }
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    return log_path
