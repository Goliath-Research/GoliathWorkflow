"""
Resolve per-action configuration from site manifest, pipeline profile, and overrides.

Study manifests (project JSON) no longer carry tool parameters. Precedence (highest wins):

  instance/program override → profile actionConfig → analyte defaults → site actionConfig → {}
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, Literal, Mapping, Optional

ActionConfigKey = Literal[
    "centroid",
    "detection",
    "dmp_selection",
    "mapper",
    "enricher",
    "classifier",
    "gene_selection",
    "predictor",
    "alignment_qc",
    "extraction_qc",
    "fragmentomics",
    "methyl_extract",
    "validation",
    "progression",
    "parabricks",
    "rna_align",
    "rna_qc",
    "rna_de_select",
]

DEFAULT_SITE_PATH = Path("/work/site/methyl_site.json")

SITE_ENV = "METHYL_SITE_CONFIG"
PROFILE_ENV = "METHYL_PROFILE"


def deep_merge(base: Dict[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(dict(out[key]), val)
        else:
            out[key] = copy.deepcopy(val)
    return out


def load_site_manifest(path: str | Path | None = None) -> Dict[str, Any]:
    raw = path or os.environ.get(SITE_ENV) or str(DEFAULT_SITE_PATH)
    p = Path(str(raw)).expanduser()
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_profile_action_config(name_or_path: str | Path | None = None) -> Dict[str, Any]:
    if name_or_path is None:
        name_or_path = os.environ.get(PROFILE_ENV)
    if not name_or_path:
        return {}
    from .profile_paths import resolve_profile_path

    try:
        profile_path = resolve_profile_path(name_or_path)
    except FileNotFoundError:
        return {}
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    action = data.get("actionConfig") or data.get("step_config_overrides") or {}
    return dict(action) if isinstance(action, dict) else {}


def site_slice_for_action(site: Mapping[str, Any], action_key: str) -> Dict[str, Any]:
    """Extract action-specific defaults from a site manifest."""
    ac = site.get("actionConfig")
    if isinstance(ac, dict) and action_key in ac and isinstance(ac[action_key], dict):
        return dict(ac[action_key])

    out: Dict[str, Any] = {}
    ref = site.get("reference_genome") or {}
    ann = site.get("annotation") or {}
    caches = site.get("caches") or {}
    pangenome = site.get("pangenome_genome") or {}

    linear_fasta = pangenome.get("linear_ref_fasta") or ref.get("fasta")

    if action_key == "alignment_qc" and linear_fasta:
        out["genome_fasta"] = linear_fasta
    if action_key in ("methyl_extract", "alignment_qc") and linear_fasta:
        out.setdefault("reference_fasta", linear_fasta)
        out.setdefault("genome_fasta", linear_fasta)
    if action_key == "mapper":
        if ann.get("gtf"):
            out["gtf"] = ann["gtf"]
        mm_home = site.get("methyl_mapper_home") or caches.get("methyl_mapper")
        if mm_home:
            out["methyl_mapper_home"] = mm_home
    if action_key == "enricher":
        nr = caches.get("string_edges")
        if nr:
            out.setdefault("network_refinement", {})["cache_path"] = nr
    if action_key == "parabricks" and site.get("parabricks"):
        out.update(dict(site["parabricks"]))
    if action_key == "methyl_extract" and site.get("methyl_extract"):
        out.update(dict(site["methyl_extract"]))
    rna_ref = site.get("rna_reference") or {}
    if isinstance(rna_ref, dict) and rna_ref:
        if action_key in ("rna_align", "rna_qc"):
            for key in ("star_index_dir", "gtf", "reference_fasta", "kallisto_index", "transcriptome_fasta", "tx2gene"):
                if rna_ref.get(key):
                    out.setdefault(key, rna_ref[key])
        if action_key == "rna_align" and site.get("parabricks"):
            for key, val in dict(site["parabricks"]).items():
                out.setdefault(key, val)
    return out


def resolve_rna_reference(site: Mapping[str, Any] | None = None) -> Dict[str, str]:
    """Resolve RNA-Seq reference assets from site manifest ``rna_reference``.

    Returns whatever keys the operator pinned. Callers validate the subset they
    need for the selected quantifier (STAR vs kallisto) so a site can ship only
    one path.
    """
    data = dict(site or load_site_manifest())
    bundle = data.get("rna_reference") or {}
    if not isinstance(bundle, dict):
        return {}
    return {str(k): str(v) for k, v in bundle.items() if v not in (None, "")}


def resolve_pangenome_genome(site: Mapping[str, Any] | None = None) -> Dict[str, str]:
    """
    Resolve pangenome graph bundle paths from site manifest ``pangenome_genome``.

    Required keys: gbz, dist, min, zipcodes, ref_paths, linear_ref_fasta.
    """
    data = dict(site or load_site_manifest())
    bundle = data.get("pangenome_genome") or {}
    if not isinstance(bundle, dict):
        bundle = {}
    required = ("gbz", "dist", "min", "zipcodes", "ref_paths", "linear_ref_fasta")
    resolved: Dict[str, str] = {}
    for key in required:
        raw = bundle.get(key)
        if raw in (None, ""):
            raise RuntimeError(
                f"site manifest pangenome_genome.{key} is required for pangenome alignment "
                f"(METHYL_SITE_CONFIG / reference_genome.fasta alone is insufficient)"
            )
        resolved[key] = str(raw)
    return resolved


def resolve_action_config(
    action_key: str,
    *,
    site: Optional[Mapping[str, Any]] = None,
    profile_action_config: Optional[Mapping[str, Any]] = None,
    program_override: Optional[Mapping[str, Any]] = None,
    instance_override: Optional[Mapping[str, Any]] = None,
    regulatory: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge configuration layers for one action catalog section."""
    site_data = dict(site or {})
    profile_all = dict(profile_action_config or {})
    merged: Dict[str, Any] = {}
    merged = deep_merge(merged, site_slice_for_action(site_data, action_key))
    section = profile_all.get(action_key)
    if isinstance(section, dict):
        merged = deep_merge(merged, section)
    for overlay in (program_override, instance_override):
        if isinstance(overlay, dict):
            merged = deep_merge(merged, overlay)

    from .analyte_profiles import merge_step_config, normalize_primary_analyte, should_apply_analyte_profile

    reg = dict(regulatory or {})
    if should_apply_analyte_profile(reg):
        analyte = normalize_primary_analyte(reg.get("primary_analyte"))
        merged = merge_step_config(action_key, merged, analyte)
    return merged


def resolve_action_config_from_env(
    action_key: str,
    *,
    regulatory: Optional[Mapping[str, Any]] = None,
    program_override: Optional[Mapping[str, Any]] = None,
    profile_path: str | Path | None = None,
    site_path: str | Path | None = None,
) -> Dict[str, Any]:
    site = load_site_manifest(site_path)
    profile = load_profile_action_config(profile_path)
    return resolve_action_config(
        action_key,
        site=site,
        profile_action_config=profile,
        program_override=program_override,
        regulatory=regulatory,
    )


def resolve_from_task_input(
    action_key: str,
    input_json: Mapping[str, Any],
    *,
    regulatory: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve config for a worker task (materialized or built at claim time)."""
    if isinstance(input_json.get("resolvedConfig"), dict):
        base = dict(input_json["resolvedConfig"])
        override = input_json.get("stepOverride")
        if isinstance(override, dict):
            return deep_merge(base, override)
        return base

    ctx = input_json.get("actionConfig")
    site = input_json.get("siteConfig")
    if isinstance(ctx, dict) and action_key in ctx:
        profile_slice = {action_key: ctx[action_key]}
    elif isinstance(ctx, dict):
        profile_slice = ctx
    else:
        profile_slice = load_profile_action_config(
            input_json.get("pipelineProfile") or input_json.get("profilePath")
        )

    site_data = site if isinstance(site, dict) else load_site_manifest(
        input_json.get("siteConfigPath")
    )
    return resolve_action_config(
        action_key,
        site=site_data,
        profile_action_config=profile_slice if isinstance(profile_slice, dict) else {},
        program_override=input_json.get("stepOverride") if isinstance(input_json.get("stepOverride"), dict) else None,
        regulatory=regulatory,
    )


def _load_json_mapping(path: str | Path) -> Dict[str, Any]:
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"resolved config JSON must be an object: {path}")
    return dict(raw)


def load_resolved_config(
    action_key: str,
    *,
    resolved_config_path: str | Path | None = None,
    resolved_config: Optional[Mapping[str, Any]] = None,
    step_override: Optional[Mapping[str, Any]] = None,
    step_override_path: str | Path | None = None,
) -> Dict[str, Any]:
    """
    Load a baked actionConfig slice from a worker ``--resolved-config`` file or dict.

    ``step_override`` / ``step_override_path`` overlay wins over the baked slice.
    Does not read project.json, profiles, or METHYL_* environment variables.
    """
    del action_key  # slice is already action-specific when passed from the worker
    if resolved_config_path not in (None, ""):
        cfg = _load_json_mapping(resolved_config_path)
    elif isinstance(resolved_config, dict):
        cfg = dict(resolved_config)
    else:
        raise ValueError("load_resolved_config requires resolved_config_path or resolved_config")

    overlay = dict(step_override) if isinstance(step_override, dict) else None
    if overlay is None and step_override_path not in (None, ""):
        overlay = _load_json_mapping(step_override_path)
    if overlay:
        return deep_merge(cfg, overlay)
    return cfg


def resolve_for_project(
    action_key: str,
    project: Any,
    *,
    step_override: Optional[Mapping[str, Any]] = None,
    resolved_config: Optional[Mapping[str, Any]] = None,
    resolved_config_path: str | Path | None = None,
    profile_path: str | Path | None = None,
    site_path: str | Path | None = None,
) -> Dict[str, Any]:
    """Resolve action config for standalone CLIs and package resolvers."""
    if resolved_config_path not in (None, "") or isinstance(resolved_config, dict):
        return load_resolved_config(
            action_key,
            resolved_config_path=resolved_config_path,
            resolved_config=resolved_config,
            step_override=step_override,
        )
    reg = project.get_regulatory_config() if hasattr(project, "get_regulatory_config") else {}
    return resolve_action_config_from_env(
        action_key,
        regulatory=reg,
        program_override=dict(step_override) if isinstance(step_override, dict) else None,
        profile_path=profile_path,
        site_path=site_path,
    )
