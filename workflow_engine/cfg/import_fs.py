"""Import filesystem / repo artifacts into a ConfigStore."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .store import ConfigStore


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def import_filesystem(
    store: ConfigStore,
    *,
    repo_root: Path | str,
    work_root: Optional[Path | str] = None,
    publish: bool = True,
    include_programs: bool = True,
    include_profiles: bool = True,
    include_site: bool = True,
    include_studies: bool = True,
    include_reference_assets: bool = True,
) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    work_root_p = Path(work_root) if work_root else None
    imported: List[str] = []
    status = "published" if publish else "draft"

    if include_reference_assets:
        endpoints_dir = (
            repo_root / "workflow_engine" / "domain" / "fixtures" / "storage_endpoints"
        )
        if endpoints_dir.is_dir():
            for path in sorted(endpoints_dir.glob("*.json")):
                doc = _load_json(path)
                name = str(doc.get("name") or path.stem)
                version = str(doc.get("version") or "1")
                body = {
                    k: v
                    for k, v in doc.items()
                    if k not in ("name", "version", "status", "credentialName")
                }
                store.upsert(
                    "storage_endpoint",
                    name,
                    body,
                    status=status,
                    version=version,
                    extra={
                        "provider": body.get("type") or "s3",
                        "credentialName": doc.get("credentialName"),
                    },
                )
                imported.append(f"storage_endpoint:{name}@{version}")

        profiles_dir = (
            repo_root / "workflow_engine" / "domain" / "fixtures" / "storage_profiles"
        )
        if profiles_dir.is_dir():
            for path in sorted(profiles_dir.glob("*.json")):
                doc = _load_json(path)
                name = str(doc.get("name") or path.stem)
                version = str(doc.get("version") or "1")
                body = {
                    k: v
                    for k, v in doc.items()
                    if k not in ("name", "version", "status")
                }
                store.upsert(
                    "storage_profile",
                    name,
                    body,
                    status=status,
                    version=version,
                )
                imported.append(f"storage_profile:{name}@{version}")

        assets_dir = (
            repo_root / "workflow_engine" / "domain" / "fixtures" / "reference_assets"
        )
        if assets_dir.is_dir():
            for path in sorted(assets_dir.glob("*.json")):
                doc = _load_json(path)
                name = str(doc.get("name") or path.stem)
                version = str(doc.get("version") or "1")
                # Store document without name/version wrapper keys if present
                body = {
                    k: v
                    for k, v in doc.items()
                    if k not in ("name", "version", "status")
                }
                store.upsert(
                    "reference_asset",
                    name,
                    body,
                    status=status,
                    version=version,
                )
                imported.append(f"reference_asset:{name}@{version}")

    if include_profiles:
        from cfg.process_pack_catalog import cfg_status_for_catalog

        profiles_dir = repo_root / "workflow_engine" / "domain" / "profiles"
        if profiles_dir.is_dir():
            for path in sorted(profiles_dir.glob("*.profile.json")):
                doc = _load_json(path)
                name = str(doc.get("pipelineProfile") or path.name.replace(".profile.json", ""))
                row_status = cfg_status_for_catalog(doc.get("catalog"))
                if row_status is None:
                    continue
                store.upsert("pipeline_profile", name, doc, status=row_status)
                imported.append(f"pipeline_profile:{name}")
            # modes/*.mode.json are overlays only — never cfg.pipeline_profile rows
            procedures_dir = profiles_dir / "procedures"
            if procedures_dir.is_dir():
                for path in sorted(procedures_dir.glob("*.procedure.json")):
                    doc = _load_json(path)
                    name = str(
                        doc.get("pipelineProcedure")
                        or path.name.replace(".procedure.json", "")
                    )
                    row_status = cfg_status_for_catalog(doc.get("catalog"))
                    if row_status is None:
                        continue
                    store.upsert("assay_procedure", name, doc, status=row_status)
                    imported.append(f"assay_procedure:{name}")

        analytes_dir = repo_root / "workflow_engine" / "domain" / "analytes"
        if analytes_dir.is_dir():
            for path in sorted(analytes_dir.glob("*.analyte.json")):
                doc = _load_json(path)
                name = str(doc.get("name") or path.name.replace(".analyte.json", ""))
                version = str(doc.get("version") or "1")
                row_status = cfg_status_for_catalog(doc.get("catalog"))
                if row_status is None:
                    continue
                store.upsert(
                    "analyte", name, doc, status=row_status, version=version
                )
                imported.append(f"analyte:{name}@{version}")

    if include_programs:
        fixtures = repo_root / "workflow_engine" / "domain" / "fixtures"
        if fixtures.is_dir():
            for path in sorted(fixtures.glob("*.program.json")):
                doc = _load_json(path)
                name = str(doc.get("name") or path.name.replace(".program.json", ""))
                store.upsert("domain_program", name, doc, status=status)
                imported.append(f"domain_program:{name}")

    if include_site and work_root_p is not None:
        site_path = work_root_p / "site" / "methyl_site.json"
        if site_path.is_file():
            doc = _load_json(site_path)
            store.upsert("site", "default", doc, status=status)
            imported.append("site:default")
        else:
            example = (
                repo_root
                / "workflow_engine"
                / "domain"
                / "profiles"
                / "site_grch38.example.json"
            )
            if example.is_file():
                store.upsert("site", "default", _load_json(example), status=status)
                imported.append("site:default(example)")
        site_rec = store.get("site", "default", published_only=False)
        assets_present = bool(
            store.list("reference_asset", published_only=True)
            or store.list("reference_asset", published_only=False)
        )
        if site_rec is not None and assets_present:
            from cfg.site_assets import link_site_assets_in_store

            try:
                plan = link_site_assets_in_store(store, site_name="default")
                imported.append(
                    "site_reference_asset:"
                    + ",".join(row["asset_role"] for row in plan.get("linked") or [])
                )
            except ValueError as exc:
                imported.append(f"site_reference_asset:skipped:{exc}")

    if include_studies and work_root_p is not None:
        projects = work_root_p / "projects"
        if projects.is_dir():
            for study_dir in sorted(p for p in projects.iterdir() if p.is_dir()):
                cfg_dir = study_dir / "configs"
                if not cfg_dir.is_dir():
                    continue
                for path in sorted(cfg_dir.glob("project_*.json")):
                    doc = _load_json(path)
                    name = path.stem.replace("project_", "", 1)
                    store.upsert(
                        "study",
                        name,
                        doc,
                        status=status,
                        extra={"studyId": study_dir.name},
                    )
                    imported.append(f"study:{name}")

    return {"imported": imported, "count": len(imported)}
