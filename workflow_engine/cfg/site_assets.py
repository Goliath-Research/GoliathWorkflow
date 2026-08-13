"""Bind site ``reference_selection`` pins to ``cfg.site_reference_asset`` roles.

``cfg.cfg_repo_link_site_asset`` is the only writer for that table. Deploy used
to seed ``cfg.reference_asset`` and never call the proc, so the portal grid was
empty on every new facility. This module is the construction caller.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from .reference_selection import (
    GENOME_SELECTION_KEYS,
    SELECTION_TO_ASSET_ROLE,
    selected_asset_names,
)
from .store import ConfigRecord, ConfigStore

# ck_cfg_sra_role in cfg_wf_relationships.sql — not a Python wish-list.
SQL_SITE_ASSET_ROLES = frozenset(
    {
        "reference_genome",
        "annotation_gtf",
        "pangenome_bundle",
        "mapper_cache",
        "houseman_seed_basis",
        "hitimed_hierarchy_basis",
        "other",
    }
)


def plan_site_asset_links(
    site_doc: Dict[str, Any],
    published_assets: Union[
        Sequence[Any],
        Mapping[str, Mapping[str, Any]],
    ],
) -> Dict[str, Any]:
    """Return ``linked`` / ``skipped`` rows for one site.

    ``pangenome_wgbs`` has no CHECK role. If stock ``pangenome`` is also pinned,
    WGBS is skipped (swap the pin / ``@links`` row for a WGBS-only site). If
    only WGBS is pinned, it occupies ``pangenome_bundle``. Dual bind is a model
    change (widen ``ck_cfg_sra_role`` and ``uq_cfg_sra_site_role``).
    """
    names = selected_asset_names(site_doc, published_assets)
    versions = _asset_versions(published_assets)
    linked: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    used_roles: set[str] = set()

    for key in GENOME_SELECTION_KEYS:
        asset_name = names.get(key)
        if not asset_name:
            continue
        role = SELECTION_TO_ASSET_ROLE.get(key)
        if role is None:
            skipped.append(
                {
                    "selection_key": key,
                    "asset_name": asset_name,
                    "reason": "no SELECTION_TO_ASSET_ROLE mapping",
                }
            )
            continue
        if role not in SQL_SITE_ASSET_ROLES:
            if "pangenome_bundle" not in used_roles and "pangenome" not in names:
                role = "pangenome_bundle"
            else:
                skipped.append(
                    {
                        "selection_key": key,
                        "asset_name": asset_name,
                        "asset_role": role,
                        "reason": (
                            "ck_cfg_sra_role has no WGBS pangenome role; "
                            "uq_cfg_sra_site_role allows one pangenome_bundle "
                            "per site (swap this asset into @links for a WGBS site)"
                        ),
                    }
                )
                continue
        if role in used_roles:
            skipped.append(
                {
                    "selection_key": key,
                    "asset_name": asset_name,
                    "asset_role": role,
                    "reason": f"uq_cfg_sra_site_role: {role} already linked",
                }
            )
            continue
        used_roles.add(role)
        linked.append(
            {
                "selection_key": key,
                "asset_name": asset_name,
                "asset_version": versions.get(asset_name, "1"),
                "asset_role": role,
            }
        )
    return {"linked": linked, "skipped": skipped}


def link_site_assets_in_store(
    store: ConfigStore,
    *,
    site_name: str = "default",
    site_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Plan links from the file store and record them on ``site.extra``."""
    site = store.get("site", site_name, version=site_version, published_only=False)
    if site is None:
        raise KeyError(f"site not found: {site_name}")
    published = store.list("reference_asset", published_only=True)
    if not published:
        published = store.list("reference_asset", published_only=False)
    plan = plan_site_asset_links(site.document, published)
    store.set_extra(
        "site",
        site.name,
        site.version,
        siteReferenceAssets=plan,
    )
    return {
        "site": site.name,
        "version": site.version,
        **plan,
    }


def apply_site_asset_links_to_db(
    db: Any,
    *,
    site_name: str,
    site_version: str,
    linked: Sequence[Mapping[str, str]],
) -> List[Dict[str, Any]]:
    """Call ``cfg.cfg_repo_link_site_asset`` for each planned row."""
    backend = str(getattr(db, "backend", "") or "").lower()
    site_row = _fetch_one(
        db,
        backend,
        mssql="SELECT TOP (1) id FROM cfg.site WHERE name=? AND version=?",
        postgres="SELECT id FROM cfg.site WHERE name=%s AND version=%s LIMIT 1",
        params=(site_name, site_version),
    )
    if not site_row or site_row.get("id") is None:
        raise KeyError(f"cfg.site {site_name}@{site_version} missing; upsert the site first")
    site_id = int(site_row["id"])
    applied: List[Dict[str, Any]] = []
    for row in linked:
        asset_name = row["asset_name"]
        asset_version = row.get("asset_version") or "1"
        role = row["asset_role"]
        asset_row = _fetch_one(
            db,
            backend,
            mssql="SELECT TOP (1) id FROM cfg.reference_asset WHERE name=? AND version=?",
            postgres=(
                "SELECT id FROM cfg.reference_asset WHERE name=%s AND version=%s LIMIT 1"
            ),
            params=(asset_name, asset_version),
        )
        if not asset_row or asset_row.get("id") is None:
            raise KeyError(
                f"cfg.reference_asset {asset_name}@{asset_version} missing; "
                "deploy cfg_reference_assets_seed.sql first"
            )
        asset_id = int(asset_row["id"])
        _exec_link(db, backend, site_id, asset_id, role)
        applied.append(
            {
                "site_id": site_id,
                "reference_asset_id": asset_id,
                "asset_name": asset_name,
                "asset_role": role,
            }
        )
    return applied


def link_site_assets(
    store: ConfigStore,
    *,
    site_name: str = "default",
    site_version: Optional[str] = None,
    db: Any = None,
) -> Dict[str, Any]:
    """File-store plan, then optionally write SQL via ``cfg_repo_link_site_asset``."""
    plan = link_site_assets_in_store(
        store, site_name=site_name, site_version=site_version
    )
    if db is None:
        return plan
    applied = apply_site_asset_links_to_db(
        db,
        site_name=plan["site"],
        site_version=plan["version"],
        linked=plan["linked"],
    )
    plan["db"] = applied
    return plan


def _asset_versions(
    published_assets: Union[Sequence[Any], Mapping[str, Mapping[str, Any]]],
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if isinstance(published_assets, Mapping):
        for name, doc in published_assets.items():
            if isinstance(doc, Mapping):
                out[str(name)] = str(doc.get("version") or "1")
            else:
                out[str(name)] = "1"
        return out
    for rec in published_assets:
        if isinstance(rec, ConfigRecord):
            out[rec.name] = rec.version
        elif isinstance(rec, Mapping) and "name" in rec:
            out[str(rec["name"])] = str(rec.get("version") or "1")
    return out


def _fetch_one(
    db: Any,
    backend: str,
    *,
    mssql: str,
    postgres: str,
    params: tuple[Any, ...],
) -> Optional[Dict[str, Any]]:
    sql = postgres if backend == "postgres" else mssql
    return db._fetch_one(sql, params)  # noqa: SLF001


def _exec_link(
    db: Any,
    backend: str,
    site_id: int,
    asset_id: int,
    role: str,
) -> None:
    if backend == "postgres":
        db._exec_proc(  # noqa: SLF001
            "SELECT * FROM cfg.cfg_repo_link_site_asset(%s, %s, %s)",
            (site_id, asset_id, role),
        )
        return
    db._exec_proc(  # noqa: SLF001
        "EXEC cfg.cfg_repo_link_site_asset "
        "@site_id=?, @reference_asset_id=?, @asset_role=?",
        (site_id, asset_id, role),
    )
