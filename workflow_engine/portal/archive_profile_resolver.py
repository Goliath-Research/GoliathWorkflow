"""Merge portal archive profiles into sample-prep study start requests."""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

DEFAULT_ARCHIVE_PROFILE_KEY = "epimethyl-samples"


def apply_archive_profile_storage(
    body: Mapping[str, Any],
    h5_storage_loader: Callable[[str], Optional[dict[str, Any]]],
    *,
    profile_key: str = DEFAULT_ARCHIVE_PROFILE_KEY,
) -> Dict[str, Any]:
    """
    Fill ``h5Storage`` from ``portal.resource_profile`` when omitted.

    ``fastqStorage`` is never inferred — initial FASTQs must come from
    laboratory-owned storage on each study start request.
    """
    out: Dict[str, Any] = dict(body)
    if out.get("fastqStorage") is None:
        raise ValueError(
            "fastqStorage is required: initial FASTQs must come from laboratory-owned "
            "storage, not from platform archive storage"
        )
    if out.get("h5Storage") is None:
        loaded = h5_storage_loader(profile_key)
        if loaded is not None:
            out["h5Storage"] = loaded
    return out
