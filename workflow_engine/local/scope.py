"""Scope variable management: collection bindings, FOREACH flattening, nested scopes."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

from workflow_definition_spec import CollectionBindingSpec, WorkflowDefinitionSpec

from .resolver import json_path_get


class ScopeFrame(MutableMapping[str, Any]):
    """Mutable scope with optional parent for nested FOREACH / PARALLEL isolation."""

    def __init__(
        self,
        initial: Optional[Mapping[str, Any]] = None,
        *,
        parent: Optional["ScopeFrame"] = None,
    ) -> None:
        self._data: Dict[str, Any] = dict(initial or {})
        self._parent = parent

    def __getitem__(self, key: str) -> Any:
        if key in self._data:
            return self._data[key]
        if self._parent is not None:
            return self._parent[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self):
        seen = set()
        if self._parent:
            for k in self._parent:
                seen.add(k)
                yield k
        for k in self._data:
            if k not in seen:
                yield k

    def __len__(self) -> int:
        return len(list(iter(self)))

    def as_flat_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self._parent:
            out.update(self._parent.as_flat_dict())
        out.update(self._data)
        return out

    def child(self, overrides: Optional[Mapping[str, Any]] = None) -> "ScopeFrame":
        return ScopeFrame(overrides or {}, parent=self)

    def copy_shallow(self) -> Dict[str, Any]:
        return dict(self.as_flat_dict())


def _read_json_file(path: str | Path) -> Any:
    p = Path(path).expanduser()
    if p.is_dir():
        candidate = p / "project.json"
        if candidate.is_file():
            p = candidate
    if not p.is_file():
        raise FileNotFoundError(f"jsonFile binding: path not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def resolve_collection_bindings(
    bindings: List[CollectionBindingSpec],
    context: Mapping[str, Any],
) -> Dict[str, Any]:
    """Apply collection_bindings at instance start (mirrors wf_resolve_collection_bindings)."""
    scope: Dict[str, Any] = dict(context)
    ordered = sorted(bindings, key=lambda b: (b.bind_order, b.scope_var))

    for binding in ordered:
        if binding.scope_var in scope and scope[binding.scope_var] not in (None, "", []):
            continue

        if binding.kind == "jsonFile":
            path_var = binding.path_var or "projectPath"
            raw_path = scope.get(path_var)
            if raw_path is None:
                if binding.scope_var in scope and isinstance(scope.get(binding.scope_var), dict):
                    continue
                raise ValueError(f"collection binding jsonFile missing path var {path_var!r}")
            try:
                scope[binding.scope_var] = _read_json_file(str(raw_path))
            except FileNotFoundError:
                if binding.scope_var in scope and scope[binding.scope_var] is not None:
                    continue
                if binding.scope_var == "project":
                    scope[binding.scope_var] = {}
                    continue
                raise

        elif binding.kind == "jsonPath":
            base_var = binding.base_var or "project"
            base = scope.get(base_var)
            if base is None:
                raise ValueError(f"collection binding jsonPath missing base var {base_var!r}")
            extracted = json_path_get(base, binding.json_path or "$")
            if extracted is None:
                raise ValueError(
                    f"collection binding jsonPath {binding.json_path!r} on {base_var!r} "
                    f"produced null for {binding.scope_var!r}"
                )
            scope[binding.scope_var] = extracted

    return scope


def flatten_foreach_element(
    element: Any,
    *,
    item_var: str,
    index_var: str,
    index: int,
) -> Dict[str, Any]:
    """Flatten FOREACH item into scope (mirrors wf_seed_foreach_iteration_scope)."""
    overrides: Dict[str, Any] = {
        item_var: element,
        index_var: index,
    }
    if isinstance(element, dict):
        for key, value in element.items():
            if key not in (item_var, index_var):
                overrides[key] = value
    return overrides


def apply_scope_defaults(
    spec: WorkflowDefinitionSpec,
    scope: MutableMapping[str, Any],
    node_key: str,
) -> None:
    for default in spec.scope_defaults:
        if default.node_key != node_key:
            continue
        var_name = default.var_name
        if var_name in scope and scope[var_name] not in (None, ""):
            continue
        expr = default.default_expr.strip()
        if expr.startswith("${var.") and expr.endswith("}"):
            src = expr[6:-1]
            if src in scope:
                scope[var_name] = scope[src]
