"""Read portal.resource_profile rows (domain config outside wf schema)."""

from __future__ import annotations

import json
from typing import Any, Optional, Protocol

from methyl_domain.platform_storage import profile_json_to_h5_storage

DEFAULT_ARCHIVE_PROFILE_KEY = "epimethyl-samples"


class _DbFetch(Protocol):
    backend: str

    def _fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]: ...


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

    def h5_storage_defaults(self, profile_key: str) -> Optional[dict[str, Any]]:
        row = self.get_active(profile_key)
        if not row:
            return None
        profile_json = row.get("profile_json")
        if not isinstance(profile_json, dict):
            return None
        return profile_json_to_h5_storage(profile_json).model_dump(mode="json")
