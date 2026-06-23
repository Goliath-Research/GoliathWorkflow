"""Apply platform sample storage from the database to sample-prep request bodies."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from methyl_domain.platform_storage import (
    DEFAULT_STORAGE_KEY,
    platform_row_to_fastq_storage,
    platform_row_to_h5_storage,
)


def apply_platform_sample_storage(
    body: Mapping[str, Any],
    row: Optional[Mapping[str, Any]],
    *,
    storage_key: str = DEFAULT_STORAGE_KEY,
) -> Dict[str, Any]:
    """
    Fill ``fastqStorage`` and ``h5Storage`` from ``wf.platform_sample_storage`` when omitted.

    Explicit values in ``body`` always win. When ``row`` is None and ``fastqStorage`` is
    missing, raises ``ValueError``.
    """
    out: Dict[str, Any] = dict(body)
    if out.get("fastqStorage") is None and row is None:
        raise ValueError(
            f"fastqStorage is required when platform storage '{storage_key}' is not configured"
        )
    if row is None:
        return out
    if out.get("fastqStorage") is None:
        out["fastqStorage"] = platform_row_to_fastq_storage(row).model_dump(mode="json")
    if out.get("h5Storage") is None:
        out["h5Storage"] = platform_row_to_h5_storage(row).model_dump(mode="json")
    return out
