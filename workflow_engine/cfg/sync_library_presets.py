"""Sync enrichment library presets from the committed registry into cfg.

Mirrors ``sync_actions``: the authored source of truth is
``packages/methylenricher/methyl_enricher/data/library_presets.json`` (loaded via
``methyl_enricher.preset_registry``); each preset is upserted as one cfg object of kind
``enrichment_library_preset`` with its resolved (default + preset) library list.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from .store import ConfigStore


def _ensure_paths(repo_root: Path) -> None:
    for p in (
        str(repo_root),
        str(repo_root / "packages" / "methylenricher"),
    ):
        if p not in sys.path:
            sys.path.insert(0, p)


def sync_library_presets_from_registry(
    store: ConfigStore,
    *,
    repo_root: Path | str,
    publish: bool = True,
) -> Dict[str, Any]:
    """Registry -> cfg: upsert each preset as an ``enrichment_library_preset`` object."""
    repo_root = Path(repo_root)
    _ensure_paths(repo_root)
    from methyl_enricher.preset_registry import load_catalog

    catalog = load_catalog()
    status = "published" if publish else "draft"
    names: List[str] = []
    for name, preset in catalog.presets.items():
        doc = {
            "name": name,
            "description": preset.description,
            "include_default": preset.include_default,
            "libraries": catalog.resolve(name),
            "catalogVersion": catalog.version,
        }
        store.upsert("enrichment_library_preset", name, doc, status=status)
        names.append(name)
    return {
        "synced": names,
        "count": len(names),
        "direction": "registry_to_cfg",
        "defaultLibraries": list(catalog.default_libraries),
    }
