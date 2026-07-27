"""Merge portal archive profiles into sample-prep study start requests."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Mapping, Optional

DEFAULT_ARCHIVE_PROFILE_KEY = "epimethyl-samples"
logger = logging.getLogger(__name__)


def apply_archive_profile_storage(
    body: Mapping[str, Any],
    sample_storage_loader: Callable[[str], Optional[dict[str, Any]]],
    *,
    profile_key: str = DEFAULT_ARCHIVE_PROFILE_KEY,
    h5_storage_loader: Callable[[str], Optional[dict[str, Any]]] | None = None,
) -> Dict[str, Any]:
    """
    Fill ``sampleStorage`` from ``portal.resource_profile`` when omitted.

    Prefer profiles that name a published ``cfg.storage_endpoint``
    (``sampleStorageEndpoint``); ``ResourceProfileReader`` expands secrets from
    the DB. Legacy inline credential JSON still works.

    ``fastqStorage`` is never inferred — initial FASTQs must come from
    laboratory-owned storage on each study start request.
    """
    loader = sample_storage_loader if h5_storage_loader is None else h5_storage_loader
    out: Dict[str, Any] = dict(body)
    if out.get("fastqStorage") is None:
        raise ValueError(
            "fastqStorage is required: initial FASTQs must come from laboratory-owned "
            "storage, not from platform archive storage"
        )
    # Compare / dry-run arms: keep outputs under sampleDir and skip QNAP fill.
    if out.get("disableArchive") is True:
        out.pop("sampleStorage", None)
        out.pop("h5Storage", None)
        return out
    if out.get("sampleStorage") is None and out.get("h5Storage") is None:
        loaded = loader(profile_key)
        if loaded is not None:
            out["sampleStorage"] = loaded
            out["h5Storage"] = loaded
    elif out.get("sampleStorage") is None and out.get("h5Storage") is not None:
        out["sampleStorage"] = out["h5Storage"]
        logger.warning("h5Storage is deprecated; use sampleStorage")
    elif out.get("h5Storage") is None and out.get("sampleStorage") is not None:
        out["h5Storage"] = out["sampleStorage"]
    return out
