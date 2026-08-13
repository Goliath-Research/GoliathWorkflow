"""Merge portal archive profiles into sample-prep study start requests."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

DEFAULT_ARCHIVE_PROFILE_KEY = "epimethyl-samples"
_STORAGE_NAME_KEYS = (
    "storageProfile",
    "fastqStorageEndpoint",
    "sampleStorageEndpoint",
)
logger = logging.getLogger(__name__)


def study_storage_defaults(project_path: str | None) -> Dict[str, Any]:
    """Read named QNAP/S3 location refs from a study project JSON."""
    if not project_path:
        return {}
    path = Path(project_path)
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(doc, dict):
        return {}
    return {k: doc[k] for k in _STORAGE_NAME_KEYS if doc.get(k)}


def _is_non_qnap_fastq(fastq: Any) -> bool:
    """True when fastqStorage is missing, a local file path, or AWS S3 (no QNAP URL)."""
    if not isinstance(fastq, dict):
        return True
    kind = str(fastq.get("type") or "")
    if kind == "file":
        return True
    endpoint = str(fastq.get("endpointUrl") or "")
    if kind == "s3" and "myqnapcloud.io" not in endpoint:
        return True
    return False


def apply_named_storage_locations(
    body: Mapping[str, Any],
    *,
    expand_endpoint: Callable[[str], Optional[dict[str, Any]]],
    load_profile: Callable[[str], Optional[dict[str, Any]]] | None = None,
    study_defaults: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Fill ``fastqStorage`` / ``sampleStorage`` from named ``cfg.storage_endpoint`` refs.

    Names come from the start body, then a ``storageProfile`` document, then the
    study project JSON. Local-file and AWS-default S3 placeholders are replaced
    when the study names a QNAP (or other) location.
    """
    out: Dict[str, Any] = dict(body)
    study = dict(study_defaults or {})
    profile_doc: Dict[str, Any] = {}
    profile_name = out.get("storageProfile") or study.get("storageProfile")
    if profile_name and load_profile is not None:
        loaded = load_profile(str(profile_name))
        if isinstance(loaded, dict):
            profile_doc = loaded.get("document") if isinstance(loaded.get("document"), dict) else loaded
            out.setdefault("storageProfile", str(profile_name))

    fastq_name = (
        out.get("fastqStorageEndpoint")
        or profile_doc.get("fastqStorageEndpoint")
        or study.get("fastqStorageEndpoint")
    )
    sample_name = (
        out.get("sampleStorageEndpoint")
        or profile_doc.get("sampleStorageEndpoint")
        or study.get("sampleStorageEndpoint")
    )

    if fastq_name and _is_non_qnap_fastq(out.get("fastqStorage")):
        expanded = expand_endpoint(str(fastq_name))
        if expanded is not None:
            out["fastqStorage"] = expanded
            out["fastqStorageEndpoint"] = str(fastq_name)

    if (
        sample_name
        and out.get("sampleStorage") is None
        and out.get("h5Storage") is None
        and out.get("disableArchive") is not True
    ):
        expanded = expand_endpoint(str(sample_name))
        if expanded is not None:
            out["sampleStorage"] = expanded
            out["h5Storage"] = expanded
            out["sampleStorageEndpoint"] = str(sample_name)
    return out


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
