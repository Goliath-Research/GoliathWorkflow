"""Execution-scope helpers for workflow instance configuration and DB sync.

An "execution scope" is the workflow engine's process-agnostic identity for one
fully-resolved configuration combination. Higher layers (cfg) map the domain
concept of a "hyperparameter" trial onto a scope; wf itself stays agnostic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from .db.base import GatewayDb


def extract_resolved_config_slices(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return all ``resolvedConfig__*`` entries from an instance context."""
    return {
        str(key): value
        for key, value in context.items()
        if str(key).startswith("resolvedConfig__")
    }


def extract_execution_scope_payload(
    context: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    """
    Build arguments for ``wf_apply_execution_scope`` from instance context.

    Reads the canonical ``executionScopeId`` and falls back to the legacy
    ``hyperparamSetId`` alias (one-release compatibility). Returns None when
    neither is present.
    """
    set_key = context.get("executionScopeId") or context.get("hyperparamSetId")
    if not set_key:
        return None
    display_name = (
        context.get("executionScopeName")
        or context.get("executionScopeLabel")
        or context.get("hyperparamSetName")
        or context.get("hyperparamSetLabel")
    )
    return {
        "set_key": str(set_key),
        "display_name": str(display_name) if display_name else None,
        "config_json": extract_resolved_config_slices(context),
    }


def sync_execution_scope_action_entry_after_submit(
    db: GatewayDb,
    node_execution_id: int,
    result_code: int,
) -> None:
    """Mirror CAAS action ledger rows into wf.execution_scope_action_entry."""
    if result_code != 0:
        return

    ctx = db.get_action_submit_context(node_execution_id)
    if not ctx:
        return

    set_key = ctx.get("execution_scope_key")
    action_name = ctx.get("action_name")
    input_json = ctx.get("input_json") or {}
    if not set_key or not action_name:
        return

    import sys
    from pathlib import Path

    workers = Path(__file__).resolve().parents[2] / "workers"
    if str(workers) not in sys.path:
        sys.path.insert(0, str(workers))

    from methyl_worker.action_catalog import find_catalog_entry
    from methyl_worker.action_execution import validate_input
    from methyl_worker.action_skip import (
        caas_enabled,
        compute_action_revision,
        compute_content_key,
        compute_input_signature,
    )
    from methyl_worker.collectors import _run_key
    from methyl_worker.task_validation import strip_runtime_input

    if not caas_enabled(input_json):
        return

    entry = find_catalog_entry(str(action_name))
    if entry is None:
        return

    task_input = strip_runtime_input(dict(input_json))
    input_model = validate_input(entry, task_input)
    revision = compute_action_revision(entry)
    input_sig = compute_input_signature(entry, dict(input_json), input_model)
    content_key = compute_content_key(revision, input_sig)

    db.upsert_execution_scope_action_entry(
        set_key=str(set_key),
        workflow_instance_id=int(ctx["workflow_instance_id"]),
        action_name=str(action_name),
        run_key=_run_key(input_json),
        content_key=content_key,
    )
