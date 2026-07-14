"""Expand named storage endpoints + credentials into worker wire-format JSON."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from .store import ConfigStore


def redact_credential(secret: Dict[str, Any]) -> Dict[str, Any]:
    """Return authMode-only view for list/portal APIs."""
    return {"authMode": secret.get("authMode", "unknown")}


def assemble_storage_location(
    location: Dict[str, Any],
    *,
    provider: str,
    prefix: Optional[str] = None,
    credential_name: Optional[str] = None,
    credential_version: Optional[str] = None,
    content_hash: Optional[str] = None,
    secret: Optional[Dict[str, Any]] = None,
    auth_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build typed ``fastqSource`` / destination JSON for workers.

    Concrete secrets are embedded for transfer modes. Vault / encrypted_file
    refs stay as references (workers resolve locally). Always attach change
    tokens ``credentialName`` / ``credentialVersion`` / ``contentHash`` when
    a named credential is used so dumb workers can refresh node-local caches.
    """
    out = deepcopy(location)
    out["type"] = provider

    if prefix is not None:
        out["prefix"] = prefix

    out.pop("credentialName", None)
    out.pop("credential_name", None)
    out.pop("authMode", None)

    if secret is not None:
        auth = str(secret.get("authMode") or "")
        # Vault / encrypted refs stay as references — workers resolve with
        # MI / Fernet / node-local cache. Do not pull Key Vault secrets into
        # the planner / task JSON.
        if auth in ("azure_key_vault", "encrypted_file"):
            out["credentials"] = {
                k: v
                for k, v in secret.items()
                if k
                in (
                    "authMode",
                    "vaultUrl",
                    "secretName",
                    "path",
                    "materializeAs",
                    "azure_key_vault_url",
                    "azure_secret_name",
                    "encrypted_file_path",
                )
            }
        else:
            out["credentials"] = deepcopy(secret)
    elif provider in ("file",):
        pass
    elif auth_hint in ("instance_profile", "default_credential", "application_default"):
        out["credentials"] = {"authMode": auth_hint}
    elif "credentials" not in out:
        if provider == "s3":
            out["credentials"] = {"authMode": "instance_profile"}
        elif provider == "azure_blob":
            out["credentials"] = {"authMode": "default_credential"}
        elif provider == "gcs":
            out["credentials"] = {"authMode": "application_default"}

    if credential_name:
        out["credentialName"] = credential_name
        if credential_version is not None:
            out["credentialVersion"] = credential_version
        if content_hash is not None:
            out["contentHash"] = content_hash
        creds = out.get("credentials")
        if isinstance(creds, dict):
            creds = dict(creds)
            creds["credentialName"] = credential_name
            if credential_version is not None:
                creds["credentialVersion"] = credential_version
            if content_hash is not None:
                creds["contentHash"] = content_hash
            out["credentials"] = creds

    return out


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
    cred_name = (
        ep.extra.get("credentialName")
        or location.get("credentialName")
        or location.get("credential_name")
    )
    auth_hint = location.get("authMode")

    secret: Optional[Dict[str, Any]] = None
    cred_ver: Optional[str] = None
    cred_hash: Optional[str] = None
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
        secret = deepcopy(cred.secret)
        cred_ver = cred.version
        cred_hash = cred.content_hash

    return assemble_storage_location(
        location,
        provider=str(provider),
        prefix=prefix,
        credential_name=cred_name,
        credential_version=cred_ver,
        content_hash=cred_hash,
        secret=secret,
        auth_hint=str(auth_hint) if auth_hint else None,
    )


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
