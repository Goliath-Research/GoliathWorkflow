"""Pipeline profile presets for composable DomainProgram workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

_PROFILES_DIR = Path(__file__).resolve().parent / "profiles"

# Scope booleans consumed by IF branches in DomainPrograms.
PIPELINE_FLAG_DEFAULTS: Dict[str, bool] = {
    "runDmpSelection": False,
    "runGeneFeaturecuts": False,
    "runBiomarkerFilter": False,
    "runGeneFeatureSelect": False,
    "stabilityFeaturecutsEnabled": False,
    "stabilityGeneFeaturecutsEnabled": False,
    "stabilityGeneBiomarkerFilterEnabled": False,
}

PROFILE_PRESETS: Dict[str, Dict[str, Any]] = {
    "legacy_dual": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": False,
        "stabilityGeneBiomarkerFilterEnabled": False,
    },
    "discovery_interpretation": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
    },
    "gene_enricher_stability": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": False,
        "stabilityGeneFeaturecutsEnabled": False,
        "stabilityGeneBiomarkerFilterEnabled": False,
    },
    "dmp_panel_stability": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": False,
    },
    "full_biomarker_gene_fc": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": True,
        "runBiomarkerFilter": True,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": True,
        "stabilityGeneBiomarkerFilterEnabled": True,
    },
    "structural_features": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": True,
    },
}


def load_profile_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_profile(name_or_path: str | Path) -> Dict[str, Any]:
    p = Path(name_or_path)
    if p.is_file():
        return load_profile_file(p)
    candidate = _PROFILES_DIR / f"{name_or_path}.profile.json"
    if candidate.is_file():
        return load_profile_file(candidate)
    if name_or_path in PROFILE_PRESETS:
        return {"pipelineProfile": name_or_path, **PROFILE_PRESETS[name_or_path]}
    raise FileNotFoundError(f"Unknown pipeline profile: {name_or_path!r}")


def _deep_merge(base: Dict[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(dict(out[key]), val)
        else:
            out[key] = val
    return out


def seed_pipeline_scope_flags(
    context: Dict[str, Any],
    *,
    step_config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Flatten validation / gene_selection / dmp_selection keys into IF-friendly scope booleans."""
    out = dict(context)
    validation = dict((step_config or {}).get("validation") or {})
    gene_sel = dict((step_config or {}).get("gene_selection") or {})
    dmp_sel = dict((step_config or {}).get("dmp_selection") or {})

    profile_name = out.get("pipelineProfile")
    preset = PROFILE_PRESETS.get(str(profile_name), {}) if profile_name else {}

    def _flag(name: str, *sources: str) -> bool:
        if name in out:
            return bool(out[name])
        if name in preset:
            return bool(preset[name])
        for src in sources:
            if src in validation:
                return bool(validation[src])
            if src in gene_sel:
                return bool(gene_sel[src])
            if src in dmp_sel:
                return bool(dmp_sel[src])
        return bool(PIPELINE_FLAG_DEFAULTS.get(name, False))

    out.setdefault(
        "stabilityFeaturecutsEnabled",
        _flag("stabilityFeaturecutsEnabled", "stability_featurecuts_enabled"),
    )
    out.setdefault(
        "stabilityGeneFeaturecutsEnabled",
        _flag("stabilityGeneFeaturecutsEnabled", "stability_gene_featurecuts_enabled"),
    )
    out.setdefault(
        "stabilityGeneBiomarkerFilterEnabled",
        _flag(
            "stabilityGeneBiomarkerFilterEnabled",
            "stability_gene_biomarker_filter_enabled",
        ),
    )
    dmp_enabled = dmp_sel.get("enabled")
    if dmp_enabled is None:
        dmp_enabled = out.get("runDmpSelection", preset.get("runDmpSelection"))
    if dmp_enabled is None:
        dmp_enabled = bool(
            out.get("stabilityFeaturecutsEnabled") or preset.get("runDmpSelection")
        )
    out.setdefault("runDmpSelection", bool(dmp_enabled))
    out.setdefault(
        "runGeneFeaturecuts",
        _flag("runGeneFeaturecuts", "stability_gene_featurecuts_enabled")
        or bool(out.get("stabilityGeneFeaturecutsEnabled")),
    )
    out.setdefault(
        "runBiomarkerFilter",
        _flag("runBiomarkerFilter", "stability_gene_biomarker_filter_enabled")
        or bool(out.get("stabilityGeneBiomarkerFilterEnabled")),
    )
    out.setdefault(
        "runGeneFeatureSelect",
        _flag("runGeneFeatureSelect", "stability_gene_feature_select_enabled"),
    )
    return out


def apply_pipeline_profile(context: Dict[str, Any], profile: Mapping[str, Any]) -> Dict[str, Any]:
    """Merge a profile dict into workflow instance context (flags + optional step_config overrides)."""
    out = dict(context)
    name = profile.get("pipelineProfile")
    if name:
        out["pipelineProfile"] = name
    preset = PROFILE_PRESETS.get(str(name), {}) if name else {}
    for key, val in {**preset, **profile}.items():
        if key in ("pipelineProfile", "step_config_overrides"):
            continue
        if isinstance(val, bool) or key in PIPELINE_FLAG_DEFAULTS:
            out[key] = bool(val)
    overrides = profile.get("step_config_overrides")
    if isinstance(overrides, dict):
        existing = dict(out.get("step_config_overrides") or {})
        out["step_config_overrides"] = _deep_merge(existing, overrides)
    return seed_pipeline_scope_flags(out, step_config=out.get("step_config_overrides"))


def apply_profile_by_name(context: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
    return apply_pipeline_profile(context, load_profile(profile_name))
