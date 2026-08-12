"""Portal process-pack catalog helpers (profiles + assay procedures)."""

from __future__ import annotations

from typing import Any, Mapping, Optional


def cfg_status_for_catalog(catalog: Mapping[str, Any] | None) -> Optional[str]:
    """Map ``catalog`` metadata to a cfg registry status, or ``None`` to skip upsert.

    - ``lifecycle=deprecated`` or ``visibility=hidden`` → ``retired``
    - ``lifecycle=active|internal`` with visibility operator/advanced → ``published``
    - missing catalog → ``published`` (legacy docs during migration)
    """
    if not isinstance(catalog, Mapping):
        return "published"
    lifecycle = str(catalog.get("lifecycle") or "active").strip().lower()
    visibility = str(catalog.get("visibility") or "operator").strip().lower()
    if lifecycle == "deprecated" or visibility == "hidden":
        return "retired"
    if lifecycle in ("active", "internal") and visibility in ("operator", "advanced"):
        return "published"
    return "retired"


def is_operator_catalog_row(
    *,
    status: str,
    catalog: Mapping[str, Any] | None,
) -> bool:
    """True when a cfg row should appear in the operator Start-wizard picker."""
    if str(status).strip().lower() != "published":
        return False
    if not isinstance(catalog, Mapping):
        return False
    return (
        str(catalog.get("visibility") or "").strip().lower() == "operator"
        and str(catalog.get("lifecycle") or "").strip().lower() == "active"
    )
