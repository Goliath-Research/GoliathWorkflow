"""Materialize published cfg objects onto shared /work (never credentials)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .kinds import MATERIALIZABLE_KINDS, Kind
from .store import ConfigStore


def _write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def materialize_paths(
    *,
    work_root: Path,
    runtime_bundle_domain: Optional[Path] = None,
) -> Dict[str, Path]:
    work_root = Path(work_root)
    bundle = runtime_bundle_domain or (
        work_root / "epimethyl" / "current" / "runtime-bundle" / "domain"
    )
    return {
        "site": work_root / "site" / "methyl_site.json",
        "storage_endpoints": work_root / "site" / "storage_endpoints",
        "storage_profiles": work_root / "site" / "storage_profiles",
        "profiles": bundle / "profiles",
        "programs": bundle / "fixtures",
        "projects": work_root / "projects",
        "action_definitions": work_root / "site" / "action_definitions",
        "reference_assets": work_root / "site" / "reference_assets",
    }


def materialize_store(
    store: ConfigStore,
    work_root: Path | str,
    *,
    runtime_bundle_domain: Optional[Path | str] = None,
    kinds: Optional[List[Kind]] = None,
    site_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Write published objects under ``work_root``. Credentials are skipped."""
    work_root = Path(work_root)
    paths = materialize_paths(
        work_root=work_root,
        runtime_bundle_domain=Path(runtime_bundle_domain)
        if runtime_bundle_domain
        else None,
    )
    selected = kinds or list(MATERIALIZABLE_KINDS)
    written: List[str] = []

    if "site" in selected:
        from .reference_selection import apply_reference_selection

        sites = store.list("site", published_only=True)
        if site_name:
            sites = [s for s in sites if s.name == site_name]
        if sites:
            # Prefer name "default" else first
            site = next((s for s in sites if s.name == "default"), sites[0])
            site_doc = apply_reference_selection(
                site.document, work_root=work_root, overwrite=False
            )
            _write_json(paths["site"], site_doc)
            written.append(f"site:{site.name}@{site.version}->{paths['site']}")

    if "pipeline_profile" in selected:
        for rec in store.list("pipeline_profile", published_only=True):
            out = paths["profiles"] / f"{rec.name}.profile.json"
            _write_json(out, rec.document)
            written.append(f"pipeline_profile:{rec.name}@{rec.version}->{out}")

    if "domain_program" in selected:
        for rec in store.list("domain_program", published_only=True):
            out = paths["programs"] / f"{rec.name}.program.json"
            _write_json(out, rec.document)
            written.append(f"domain_program:{rec.name}@{rec.version}->{out}")

    if "study" in selected:
        from .study_membership import materialize_study_membership

        # Membership CSVs + synced sample_paths (when extra.studyGroups present)
        mem = materialize_study_membership(store, work_root)
        for path in mem.get("written") or []:
            written.append(f"study_membership:{path}")

        for rec in store.list("study", published_only=True):
            study_id = (
                rec.extra.get("studyId")
                or rec.document.get("study_id")
                or rec.document.get("studyId")
                or rec.name
            )
            cfg_dir = paths["projects"] / str(study_id) / "configs"
            out = cfg_dir / f"project_{rec.name}.json"
            _write_json(out, rec.document)
            (paths["projects"] / str(study_id) / "data").mkdir(parents=True, exist_ok=True)
            written.append(f"study:{rec.name}@{rec.version}->{out}")

    if "storage_endpoint" in selected:
        for rec in store.list("storage_endpoint", published_only=True):
            # Non-secret location only
            meta = {
                "name": rec.name,
                "version": rec.version,
                "provider": rec.extra.get("provider") or rec.document.get("type"),
                "location": rec.document,
                "credentialName": rec.extra.get("credentialName")
                or rec.document.get("credentialName"),
            }
            out = paths["storage_endpoints"] / f"{rec.name}.json"
            _write_json(out, meta)
            written.append(f"storage_endpoint:{rec.name}@{rec.version}->{out}")

    if "storage_profile" in selected:
        for rec in store.list("storage_profile", published_only=True):
            out = paths["storage_profiles"] / f"{rec.name}.json"
            _write_json(out, rec.document)
            written.append(f"storage_profile:{rec.name}@{rec.version}->{out}")

    if "reference_asset" in selected:
        for rec in store.list("reference_asset", published_only=True):
            out = paths["reference_assets"] / f"{rec.name}@{rec.version}.json"
            _write_json(out, rec.document)
            # Convenience alias for the published version (last write wins if multiple)
            alias = paths["reference_assets"] / f"{rec.name}.json"
            _write_json(alias, rec.document)
            written.append(f"reference_asset:{rec.name}@{rec.version}->{out}")

    if "action_definition" in selected:
        for rec in store.list("action_definition", published_only=True):
            out = paths["action_definitions"] / f"{rec.name}.json"
            _write_json(out, rec.document)
            written.append(f"action_definition:{rec.name}@{rec.version}->{out}")

    return {"workRoot": str(work_root), "written": written, "paths": {k: str(v) for k, v in paths.items()}}
