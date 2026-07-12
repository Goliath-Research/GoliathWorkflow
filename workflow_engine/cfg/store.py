"""File-backed config store (local/CI stand-in for cfg.* tables)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .kinds import CFG_KINDS, Kind

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def content_hash(doc: Any) -> str:
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_name(name: str) -> str:
    return _SAFE.sub("_", name).strip("._") or "unnamed"


@dataclass
class ConfigRecord:
    kind: Kind
    name: str
    version: str
    status: str
    content_hash: str
    document: Dict[str, Any]
    secret: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    id: Optional[int] = None


class ConfigStore:
    """Abstract registry API used by methyl-cfg."""

    def upsert(
        self,
        kind: Kind,
        name: str,
        document: Dict[str, Any],
        *,
        version: str = "1",
        status: str = "draft",
        secret: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ConfigRecord:
        raise NotImplementedError

    def get(
        self,
        kind: Kind,
        name: str,
        *,
        version: Optional[str] = None,
        published_only: bool = False,
        include_secret: bool = False,
    ) -> Optional[ConfigRecord]:
        raise NotImplementedError

    def list(
        self, kind: Kind, *, published_only: bool = False
    ) -> List[ConfigRecord]:
        raise NotImplementedError

    def publish(self, kind: Kind, name: str, version: str) -> ConfigRecord:
        raise NotImplementedError

    def set_extra(
        self, kind: Kind, name: str, version: str, **extra: Any
    ) -> ConfigRecord:
        raise NotImplementedError


class FileConfigStore(ConfigStore):
    """Persist cfg objects as JSON under ``store_dir/<kind>/<name>__<version>.json``."""

    def __init__(self, store_dir: Path | str) -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        for kind in CFG_KINDS:
            (self.store_dir / kind).mkdir(parents=True, exist_ok=True)

    def _path(self, kind: Kind, name: str, version: str) -> Path:
        return self.store_dir / kind / f"{_safe_name(name)}__{_safe_name(version)}.json"

    def _load(self, path: Path) -> ConfigRecord:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ConfigRecord(
            kind=raw["kind"],
            name=raw["name"],
            version=raw["version"],
            status=raw.get("status", "draft"),
            content_hash=raw.get("content_hash", ""),
            document=raw.get("document") or {},
            secret=raw.get("secret"),
            extra=raw.get("extra") or {},
            id=raw.get("id"),
        )

    def _save(self, rec: ConfigRecord) -> ConfigRecord:
        path = self._path(rec.kind, rec.name, rec.version)
        payload = {
            "kind": rec.kind,
            "name": rec.name,
            "version": rec.version,
            "status": rec.status,
            "content_hash": rec.content_hash,
            "document": rec.document,
            "extra": rec.extra,
        }
        if rec.secret is not None:
            payload["secret"] = rec.secret
        if rec.id is not None:
            payload["id"] = rec.id
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return rec

    def upsert(
        self,
        kind: Kind,
        name: str,
        document: Dict[str, Any],
        *,
        version: str = "1",
        status: str = "draft",
        secret: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ConfigRecord:
        if kind not in CFG_KINDS:
            raise ValueError(f"unknown kind: {kind}")
        if kind == "credential" and secret is None:
            secret = document
            document = {
                "provider": secret.get("provider")
                or (extra or {}).get("provider")
                or "unknown",
                "authMode": secret.get("authMode", "unknown"),
            }
        existing = self.get(kind, name, version=version)
        h = content_hash(secret if kind == "credential" else document)
        rec = ConfigRecord(
            kind=kind,
            name=name,
            version=version,
            status=status,
            content_hash=h,
            document=document,
            secret=secret if kind == "credential" else None,
            extra={**(existing.extra if existing else {}), **(extra or {})},
            id=(existing.id if existing else None) or abs(hash(f"{kind}:{name}:{version}")) % (10**9),
        )
        return self._save(rec)

    def get(
        self,
        kind: Kind,
        name: str,
        *,
        version: Optional[str] = None,
        published_only: bool = False,
        include_secret: bool = False,
    ) -> Optional[ConfigRecord]:
        kind_dir = self.store_dir / kind
        if not kind_dir.is_dir():
            return None
        candidates: List[ConfigRecord] = []
        for path in sorted(kind_dir.glob("*.json")):
            rec = self._load(path)
            if rec.name != name:
                continue
            if version is not None and rec.version != version:
                continue
            if published_only and rec.status != "published":
                continue
            candidates.append(rec)
        if not candidates:
            return None
        # Prefer exact version match; else latest by path order / id
        if version is None:
            candidates.sort(key=lambda r: (r.status != "published", -int(r.id or 0)))
        rec = candidates[0]
        if kind == "credential" and not include_secret:
            rec = ConfigRecord(
                kind=rec.kind,
                name=rec.name,
                version=rec.version,
                status=rec.status,
                content_hash=rec.content_hash,
                document={"provider": rec.document.get("provider"), "authMode": rec.document.get("authMode")},
                secret=None,
                extra=rec.extra,
                id=rec.id,
            )
        return rec

    def list(self, kind: Kind, *, published_only: bool = False) -> List[ConfigRecord]:
        kind_dir = self.store_dir / kind
        if not kind_dir.is_dir():
            return []
        out: List[ConfigRecord] = []
        for path in sorted(kind_dir.glob("*.json")):
            rec = self._load(path)
            if published_only and rec.status != "published":
                continue
            if kind == "credential":
                rec.secret = None
            out.append(rec)
        return out

    def publish(self, kind: Kind, name: str, version: str) -> ConfigRecord:
        rec = self.get(kind, name, version=version, include_secret=True)
        if rec is None:
            raise KeyError(f"{kind}/{name}@{version} not found")
        rec.status = "published"
        return self._save(rec)

    def set_extra(
        self, kind: Kind, name: str, version: str, **extra: Any
    ) -> ConfigRecord:
        rec = self.get(kind, name, version=version, include_secret=True)
        if rec is None:
            raise KeyError(f"{kind}/{name}@{version} not found")
        rec.extra.update(extra)
        return self._save(rec)
