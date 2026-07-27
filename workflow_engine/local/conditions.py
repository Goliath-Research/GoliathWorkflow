"""IF/SWITCH/WHILE condition evaluation (mirrors wf_sql_branch_parity semantics)."""

from __future__ import annotations

from typing import Any, Mapping


def scope_var_truthy(scope: Mapping[str, Any], var_name: str) -> bool:
    """
    Evaluate workflow branch condition from a scope variable.

    Matches SQL ``wf_get_scope_variable_int`` truthiness: non-zero integers,
    JSON/Python booleans (true→1 / false→0), non-empty strings; false/0/empty/null
    are falsy. SQL must coerce JSON ``true``/``false`` the same way (engine-generic).
    """
    if var_name not in scope:
        return False
    val = scope[var_name]
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("", "0", "false", "null", "none"):
            return False
        return True
    if isinstance(val, (list, dict)):
        return len(val) > 0
    return bool(val)


def scope_var_int(scope: Mapping[str, Any], var_name: str) -> int:
    """Coerce scope variable to int for SWITCH case matching."""
    if var_name not in scope:
        return 0
    val = scope[var_name]
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        s = val.strip()
        if s.lower() in ("", "false", "null"):
            return 0
        if s.lower() == "true":
            return 1
        try:
            return int(s)
        except ValueError:
            return 0
    return 0
