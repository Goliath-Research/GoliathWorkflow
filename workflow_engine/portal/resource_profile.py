"""Read portal.resource_profile rows and resolve cfg.storage_endpoint refs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional, Protocol

from methyl_domain.platform_storage import profile_json_to_h5_storage_dict

DEFAULT_ARCHIVE_PROFILE_KEY = "epimethyl-samples"

_CFG_DIR = Path(__file__).resolve().parents[1] / "cfg"
if str(_CFG_DIR) not in sys.path:
    sys.path.insert(0, str(_CFG_DIR.parent))


class _DbFetch(Protocol):
    backend: str

    def _fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]: ...


def _parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


class ResourceProfileReader:
    """Load active resource profiles from portal schema via gateway DB connection."""

    def __init__(self, db: _DbFetch) -> None:
        self._db = db

    def get_active(self, profile_key: str) -> Optional[dict[str, Any]]:
        if self._db.backend == "postgres":
            row = self._db._fetch_one(
                """
                SELECT profile_key, profile_type, profile_json, status
                FROM portal.resource_profile
                WHERE profile_key = %s AND status = 'ACTIVE'
                """,
                (profile_key,),
            )
        else:
            row = self._db._fetch_one(
                """
                SELECT profile_key, profile_type, profile_json, status
                FROM portal.resource_profile
                WHERE profile_key = ? AND status = 'ACTIVE'
                """,
                (profile_key,),
            )
        if not row:
            return None
        raw = row.get("profile_json")
        if isinstance(raw, str):
            row = dict(row)
            row["profile_json"] = json.loads(raw)
        return row

    def _expand_storage_endpoint(
        self, endpoint_name: str, *, prefix_base: str | None = None
    ) -> Optional[dict[str, Any]]:
        """Load published endpoint + credential from cfg and assemble worker JSON."""
        from cfg.storage_expand import assemble_storage_location

        if self._db.backend == "postgres":
            row = self._db._fetch_one(
                """
                SELECT e.location_json, e.provider, e.credential_name, e.version AS endpoint_version,
                       c.secret_json, c.content_hash, c.version AS cred_version, c.auth_mode
                FROM cfg.storage_endpoint e
                LEFT JOIN LATERAL (
                    SELECT secret_json, content_hash, version, auth_mode
                    FROM cfg.credential
                    WHERE name = e.credential_name AND status = 'published'
                    ORDER BY id DESC
                    LIMIT 1
                ) c ON true
                WHERE e.name = %s AND e.status = 'published'
                ORDER BY e.id DESC
                LIMIT 1
                """,
                (endpoint_name,),
            )
        else:
            row = self._db._fetch_one(
                """
                SELECT TOP 1
                       e.location_json, e.provider, e.credential_name, e.version AS endpoint_version,
                       c.secret_json, c.content_hash, c.version AS cred_version, c.auth_mode
                FROM cfg.storage_endpoint e
                OUTER APPLY (
                    SELECT TOP 1 secret_json, content_hash, version, auth_mode
                    FROM cfg.credential
                    WHERE name = e.credential_name AND status = 'published'
                    ORDER BY id DESC
                ) c
                WHERE e.name = ? AND e.status = 'published'
                ORDER BY e.id DESC
                """,
                (endpoint_name,),
            )
        if not row:
            return None
        location = _parse_json_field(row.get("location_json")) or {}
        if not isinstance(location, dict):
            return None
        secret = _parse_json_field(row.get("secret_json"))
        if secret is not None and not isinstance(secret, dict):
            secret = None
        credential_name = row.get("credential_name")
        # Match expand_storage_endpoint: named credential must resolve to a
        # published secret. LEFT JOIN + missing/unpublished cred must not fall
        # through to ambient auth (e.g. instance_profile) with credentialName set.
        if credential_name and secret is None:
            raise KeyError(f"credential not found: {credential_name}")
        provider = (
            row.get("provider")
            or location.get("type")
            or location.get("provider")
            or "file"
        )
        # sampleStorage defaults use prefixBase (not per-sample prefix). Leave
        # prefix unset so SampleStorageDefaults (extra=forbid) accepts the dict.
        assembled = assemble_storage_location(
            location,
            provider=str(provider),
            prefix=None,
            credential_name=credential_name,
            credential_version=row.get("cred_version"),
            content_hash=row.get("content_hash"),
            secret=secret,
        )
        assembled.pop("prefix", None)
        if prefix_base:
            assembled["prefixBase"] = str(prefix_base)
        elif assembled.get("prefixBase") is None and location.get("prefixBase"):
            assembled["prefixBase"] = location.get("prefixBase")
        return assembled

    def expand_endpoint(
        self, endpoint_name: str, *, prefix_base: str | None = None
    ) -> Optional[dict[str, Any]]:
        """Public wrapper: expand a published ``cfg.storage_endpoint`` name."""
        return self._expand_storage_endpoint(endpoint_name, prefix_base=prefix_base)

    def get_storage_profile(self, profile_name: str) -> Optional[dict[str, Any]]:
        """Load a published ``cfg.storage_profile`` document (endpoint name pairing)."""
        if self._db.backend == "postgres":
            row = self._db._fetch_one(
                """
                SELECT document_json
                FROM cfg.storage_profile
                WHERE name = %s AND status = 'published'
                ORDER BY id DESC
                LIMIT 1
                """,
                (profile_name,),
            )
        else:
            row = self._db._fetch_one(
                """
                SELECT TOP 1 document_json
                FROM cfg.storage_profile
                WHERE name = ? AND status = 'published'
                ORDER BY id DESC
                """,
                (profile_name,),
            )
        if not row:
            return None
        doc = _parse_json_field(row.get("document_json"))
        return doc if isinstance(doc, dict) else None

    def h5_storage_defaults(self, profile_key: str) -> Optional[dict[str, Any]]:
        row = self.get_active(profile_key)
        if not row:
            return None
        profile_json = row.get("profile_json")
        if not isinstance(profile_json, dict):
            return None
        endpoint_name = (
            profile_json.get("sampleStorageEndpoint")
            or profile_json.get("storageEndpoint")
        )
        if endpoint_name:
            expanded = self._expand_storage_endpoint(
                str(endpoint_name),
                prefix_base=profile_json.get("prefixBase"),
            )
            if expanded is not None:
                return expanded
            return None
        return profile_json_to_h5_storage_dict(profile_json)
