"""FOREACH iteration-bundle CAAS helpers for local and DB engines.

Local scheduler probes/commits ``.caas/foreach_bundle/{content_key}/``.
DB engines mirror hits into ``wf.foreach_bundle_entry`` (see sql_pg/08_foreach_support.sql)
so ``wf_try_bind_foreach_body`` can skip BODY fan-out without claiming leaf ACTIONs.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)


def foreach_caas_enabled(scope_values: Mapping[str, Any] | None = None) -> bool:
    if scope_values and scope_values.get("foreachCaasEnabled") is False:
        return False
    if scope_values and scope_values.get("forceRerun") is True:
        return False
    env = os.environ.get("METHYL_FOREACH_CAAS_ENABLED", "").strip().lower()
    if env in {"0", "false", "no", "off"}:
        return False
    return True


def collect_body_action_names(graph: Any, body_key: Optional[str]) -> List[str]:
    """DFS collect ACTION names under a FOREACH BODY (stable order)."""
    if not body_key:
        return []
    names: List[str] = []
    seen: set[str] = set()

    def walk(key: str) -> None:
        if key in seen:
            return
        seen.add(key)
        node = graph.nodes.get(key)
        if node is None:
            return
        if node.node_type == "ACTION" and node.action_name:
            names.append(str(node.action_name))
        for branch in ("SEQUENCE", "BODY", "THEN", "ELSE", "PARALLEL", "CASE", "DEFAULT"):
            for child in graph.child_keys(key, branch):
                walk(child)

    walk(body_key)
    return names


def child_action_revisions(action_names: Sequence[str]) -> List[str]:
    revisions: List[str] = []
    try:
        from methyl_worker.action_catalog import find_catalog_entry
        from methyl_worker.action_skip import compute_action_revision
    except Exception:
        return [f"{name}:unknown" for name in action_names]
    for name in action_names:
        entry = find_catalog_entry(name)
        if entry is None:
            revisions.append(f"{name}:unknown")
            continue
        revisions.append(f"{name}:{compute_action_revision(entry)}")
    return revisions


def canonical_item_payload(element: Any) -> Any:
    """JSON-stable form of a FOREACH item for content keys."""
    if isinstance(element, (str, int, float, bool)) or element is None:
        return element
    if isinstance(element, Mapping):
        # Prefer path-like keys remapped later by study signatures; keep structure.
        return {str(k): canonical_item_payload(v) for k, v in sorted(element.items())}
    if isinstance(element, (list, tuple)):
        return [canonical_item_payload(v) for v in element]
    return str(element)


def probe_iteration_bundle(
    project_root: Optional[Path],
    *,
    foreach_node_key: str,
    collection_var: str,
    iteration_index: int,
    item_payload: Any,
    child_revisions: Sequence[str],
    enabled: bool = True,
    extra_input_fingerprint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not enabled or project_root is None:
        return None
    from methyl_domain.foreach_bundle import try_short_circuit_foreach_iteration

    return try_short_circuit_foreach_iteration(
        project_root,
        foreach_node_key=foreach_node_key,
        collection_var=collection_var,
        iteration_index=iteration_index,
        item_payload=item_payload,
        child_action_revisions=list(child_revisions),
        extra_input_fingerprint=extra_input_fingerprint,
        enabled=True,
    )


def commit_iteration_bundle_local(
    project_root: Optional[Path],
    *,
    foreach_node_key: str,
    collection_var: str,
    iteration_index: int,
    item_payload: Any,
    child_revisions: Sequence[str],
    enabled: bool = True,
    extra_input_fingerprint: Optional[str] = None,
) -> Optional[Path]:
    if not enabled or project_root is None:
        return None
    from methyl_domain.foreach_bundle import (
        commit_iteration_bundle,
        compute_iteration_bundle_key,
    )

    key = compute_iteration_bundle_key(
        foreach_node_key=foreach_node_key,
        collection_var=collection_var,
        iteration_index=iteration_index,
        item_payload=item_payload,
        child_action_revisions=list(child_revisions),
        extra_input_fingerprint=extra_input_fingerprint,
    )
    path = commit_iteration_bundle(
        project_root,
        key,
        foreach_node_key=foreach_node_key,
        collection_var=collection_var,
        iteration_index=iteration_index,
        item_payload=item_payload,
        child_content_keys={},
        status="completed",
    )
    logger.debug(
        "FOREACH CAAS commit node=%s iter=%s key=%s",
        foreach_node_key,
        iteration_index,
        key[:12],
    )
    return path


def db_bundle_row_payload(
    *,
    content_key: str,
    foreach_node_key: str,
    collection_var: str,
    iteration_index: int,
    status: str = "completed",
) -> Dict[str, Any]:
    """Payload shape for ``wf.foreach_bundle_entry`` upserts (gateway/DB path)."""
    return {
        "content_key": content_key,
        "foreach_node_key": foreach_node_key,
        "collection_var": collection_var,
        "iteration_index": int(iteration_index),
        "status": status,
        "manifest_json": json.dumps(
            {
                "schema_version": "foreach_bundle_v1",
                "content_key": content_key,
                "foreach_node_key": foreach_node_key,
                "collection_var": collection_var,
                "iteration_index": int(iteration_index),
                "status": status,
            },
            sort_keys=True,
        ),
    }
