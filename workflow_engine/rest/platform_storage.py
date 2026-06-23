"""Apply platform archive storage from the database to sample-prep request bodies."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from methyl_domain.platform_storage import (
    DEFAULT_STORAGE_KEY,
    platform_row_to_h5_storage,
)


def apply_platform_archive_storage(
    body: Mapping[str, Any],
    row: Optional[Mapping[str, Any]],
    *,
    storage_key: str = DEFAULT_STORAGE_KEY,
) -> Dict[str, Any]:
    """
    Fill ``h5Storage`` from ``wf.platform_sample_storage`` when omitted.

    ``fastqStorage`` is never inferred from the platform row — initial FASTQs always
    come from laboratory-owned storage and must be supplied on each study start request.
    """
    out: Dict[str, Any] = dict(body)
    if out.get("fastqStorage") is None:
        raise ValueError(
            "fastqStorage is required: initial FASTQs must come from laboratory-owned "
            "storage, not from platform archive storage"
        )
    if row is None:
        return out
    if out.get("h5Storage") is None:
        out["h5Storage"] = platform_row_to_h5_storage(row).model_dump(mode="json")
    return out
