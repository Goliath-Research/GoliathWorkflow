"""
Prefix remapping for pipeline project JSON (e.g. different NFS mount between machines).
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def remap_path_string(path: str, path_remap: Dict[str, str]) -> str:
    """
    Replace the longest matching old prefix in ``path_remap`` (same rule as methyl-classifier).
    """
    if not path_remap or not path:
        return path
    best_old: Optional[str] = None
    for old_prefix in path_remap:
        if path.startswith(old_prefix) and (best_old is None or len(old_prefix) > len(best_old)):
            best_old = old_prefix
    if best_old is not None:
        new_prefix = path_remap[best_old]
        rest = path[len(best_old) :].lstrip("/")
        return f"{new_prefix.rstrip('/')}/{rest}" if rest else new_prefix.rstrip("/")
    return path


def apply_path_remap_to_nested(obj: Any, path_remap: Dict[str, str]) -> None:
    """
    In-place: remap every string value in nested dicts/lists (typical project JSON).
    """
    if not path_remap:
        return
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = remap_path_string(v, path_remap)
            else:
                apply_path_remap_to_nested(v, path_remap)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = remap_path_string(v, path_remap)
            else:
                apply_path_remap_to_nested(v, path_remap)
