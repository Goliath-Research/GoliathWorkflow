"""Expand named storage endpoints + credentials into worker wire-format JSON."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from .store import ConfigStore


def redact_credential(secret: Dict[str, Any]) -> Dict[str, Any]:
    """Return authMode-only view for list/portal APIs."""
    return {"authMode": secret.get("authMode", "unknown")}


def expand_storage_endpoint(
    store: ConfigStore,
    endpoint_name: str,
    *,
    prefix: Optional[str] = None,
    endpoint_version: Optional[str] = None,
    credential_version: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build typed ``fastqSource`` / destination JSON for workers.

    Location comes from ``cfg.storage_endpoint``; secrets from ``cfg.credential``
    referenced by ``credentialName`` (or embedded auth modes that need no secret).
    """
    ep = store.get(
        "storage_endpoint",
        endpoint_name,
        version=endpoint_version,
        published_only=True,
    )
    if ep is None:
        # Fall back to any status for local draft workflows
        ep = store.get("storage_endpoint", endpoint_name, version=endpoint_version)
    if ep is None:
        raise KeyError(f"storage_endpoint not found: {endpoint_name}")

    location = deepcopy(ep.document)
    provider = (
        ep.extra.get("provider")
        or location.get("type")
        or location.get("provider")
        or "file"
    )
    location["type"] = provider

    if prefix is not None:
        location["prefix"] = prefix

    cred_name = (
        ep.extra.get("credentialName")
        or location.pop("credentialName", None)
        or location.pop("credential_name", None)
    )
    auth_hint = location.pop("authMode", None)

    if cred_name:
        cred = store.get(
            "credential",
            cred_name,
            version=credential_version,
            published_only=False,
            include_secret=True,
        )
        if cred is None or not cred.secret:
            raise KeyError(f"credential not found: {cred_name}")
        location["credentials"] = deepcopy(cred.secret)
    elif provider in ("file",):
        pass
    elif auth_hint in ("instance_profile", "default_credential", "application_default"):
        location["credentials"] = {"authMode": auth_hint}
    elif "credentials" not in location:
        # Non-secret auth modes may live on the endpoint document
        if provider == "s3":
            location["credentials"] = {"authMode": "instance_profile"}
        elif provider == "azure_blob":
            location["credentials"] = {"authMode": "default_credential"}
        elif provider == "gcs":
            location["credentials"] = {"authMode": "application_default"}

    return location


def expand_storage_profile(
    store: ConfigStore,
    profile_name: str,
    *,
    sample_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Expand a storage_profile document that references named endpoints.

    Expected profile shape::

        {
          "fastqStorageEndpoint": "lab-aws",
          "sampleStorageEndpoint": "archive-azure",
          ...
        }
    """
    rec = store.get("storage_profile", profile_name, published_only=True) or store.get(
        "storage_profile", profile_name
    )
    if rec is None:
        raise KeyError(f"storage_profile not found: {profile_name}")
    doc = deepcopy(rec.document)
    out: Dict[str, Any] = {"name": profile_name, "document": doc}
    if doc.get("fastqStorageEndpoint"):
        out["fastqStorage"] = expand_storage_endpoint(
            store, doc["fastqStorageEndpoint"], prefix=sample_prefix
        )
    if doc.get("sampleStorageEndpoint"):
        out["sampleStorage"] = expand_storage_endpoint(
            store, doc["sampleStorageEndpoint"], prefix=sample_prefix
        )
    return out
