"""Template and placeholder resolution for local workflow engine."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional

_PLACEHOLDER_RE = re.compile(r"^\$\{var\.([^}]+)\}$")
_INDEXED_RE = re.compile(r"^(.+)\[(\d+)\]$")


def _get_scope_value(scope: Mapping[str, Any], key: str) -> Any:
    if key in scope:
        return scope[key]
    if "." in key:
        parts = key.split(".")
        cur: Any = scope
        for part in parts:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                raise KeyError(f"unresolved scope variable: {key}")
        return cur
    raise KeyError(f"unresolved scope variable: {key}")


def _resolve_indexed(key: str, scope: Mapping[str, Any]) -> Any:
    m = _INDEXED_RE.match(key)
    if not m:
        return _get_scope_value(scope, key)
    base, idx_s = m.group(1), int(m.group(2))
    base_val = _get_scope_value(scope, base)
    if isinstance(base_val, list):
        return base_val[idx_s]
    if isinstance(base_val, dict):
        keys = list(base_val.keys())
        return base_val[keys[idx_s]]
    raise KeyError(f"cannot index scope variable: {key}")


def resolve_placeholder(
    value: Any, scope: Mapping[str, Any], *, missing: str = "error"
) -> Any:
    """Resolve ``${var.name}`` and ``${var.name[n]}`` placeholders.

    missing: ``error`` raises KeyError; ``none`` yields None for absent vars.
    """
    if isinstance(value, dict):
        return {
            k: resolve_placeholder(v, scope, missing=missing) for k, v in value.items()
        }
    if isinstance(value, list):
        return [resolve_placeholder(v, scope, missing=missing) for v in value]
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    m = _PLACEHOLDER_RE.match(stripped)
    if not m:
        return value
    key = m.group(1)
    try:
        return _resolve_indexed(key, scope)
    except KeyError:
        if missing == "none":
            return None
        raise


def resolve_input_template(
    template: Mapping[str, Any], scope: Mapping[str, Any]
) -> Dict[str, Any]:
    resolved = resolve_placeholder(dict(template), scope, missing="none")
    return {k: v for k, v in resolved.items() if v is not None}


def list_unresolved_placeholders(value: Any) -> List[str]:
    found: set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, str):
            m = _PLACEHOLDER_RE.match(obj.strip())
            if m:
                found.add(m.group(1))

    walk(value)
    return sorted(found)


def json_path_get(doc: Any, json_path: str) -> Any:
    """Extract value at ``$.a.b`` JSONPath-style (limited)."""
    if not json_path or json_path in ("$", "$."):
        return doc
    path = json_path.lstrip("$").lstrip(".")
    if not path:
        return doc
    cur = doc
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def extract_json_path_value(output: Mapping[str, Any], json_path: str) -> Any:
    """Read worker output_json at ``$.field`` path."""
    if not json_path:
        return None
    if json_path.startswith("$."):
        return json_path_get(output, json_path)
    return json_path_get(output, f"$.{json_path}")
