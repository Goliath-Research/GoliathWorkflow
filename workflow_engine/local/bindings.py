"""Apply output_bindings and action-catalog scope_bindings after ACTION execution."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping

from pydantic import BaseModel

from workflow_definition_spec import WorkflowDefinitionSpec, WorkflowOutputBindingSpec

from .resolver import extract_json_path_value

_WORKERS = Path(__file__).resolve().parents[2] / "workers"
if str(_WORKERS) not in sys.path:
    sys.path.insert(0, str(_WORKERS))


def _bindings_for_node(
    spec: WorkflowDefinitionSpec, node_key: str
) -> List[WorkflowOutputBindingSpec]:
    return [b for b in spec.output_bindings if b.node_key == node_key]


def _output_fields(output: BaseModel) -> Mapping[str, Any]:
    """Scope bindings read typed ACTION outputs via their declared fields."""
    return output.model_dump(mode="python")


def apply_output_bindings(
    spec: WorkflowDefinitionSpec,
    node_key: str,
    output: BaseModel,
    scope: MutableMapping[str, Any],
) -> None:
    """Write workflow output_bindings into scope."""
    output_fields = _output_fields(output)
    for binding in _bindings_for_node(spec, node_key):
        if binding.source_kind == "result_code":
            val = output_fields.get("result_code", 0)
            scope[binding.var_name] = val
            continue
        path = binding.source_json_path or ""
        val = extract_json_path_value(output_fields, path)
        if val is not None:
            scope[binding.var_name] = val


def apply_catalog_scope_bindings(
    action_name: str,
    output: BaseModel,
    scope: MutableMapping[str, Any],
) -> None:
    """Apply domain_effects.scope_bindings from action catalog (safety net)."""
    from methyl_worker.action_catalog import find_catalog_entry

    entry = find_catalog_entry(action_name)
    if entry is None or not entry.domain_effects:
        return
    output_fields = _output_fields(output)
    for var_name, json_path in entry.domain_effects.scope_bindings:
        if var_name in scope and scope[var_name] not in (None, ""):
            continue
        val = extract_json_path_value(output_fields, json_path)
        if val is not None:
            scope[var_name] = val
