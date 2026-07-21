"""Pipeline profile presets for composable DomainProgram workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

# Deprecated profile names → canonical file (preset flags also aliased in PROFILE_PRESETS).
_PROFILE_ALIASES: Dict[str, str] = {
    "buffy_mc_gene_fc": "mc_dmp_gene_fc",
    "gene_enricher_stability": "mc_dmp",
    "dmp_panel_stability": "mc_dmp_fc",
    "mc_dmp_discovery": "mc_dmp",
    "mc_dmp_featurecuts": "mc_dmp_fc",
    "mc_gene_mapper": "mc_gene",
    "mc_gene_featurecuts": "mc_gene_fc",
    "discovery_gene_featurecuts": "mc_dmp_gene_fc",
}

# Legacy mc_* research axes → samd_research + named mode overlay (profiles/modes/*.mode.json).
_SAMD_RESEARCH_MODES: Dict[str, str] = {
    "mc_dmp": "dmp_raw",
    "mc_dmp_fc": "dmp_fc",
    "mc_gene": "gene_enricher",
    "mc_gene_fc": "gene_fc",
    "mc_dmp_gene_fc": "dual_fc",
}

_RESEARCH_MODE_IDS = frozenset(_SAMD_RESEARCH_MODES.values())

_STRING_SCOPE_KEYS = frozenset(
    {"researchMode", "dmp_modeling_mode", "gene_modeling_mode"}
)

PIPELINE_FLAG_DEFAULTS: Dict[str, bool] = {
    "usePangenome": False,
    "useEpiGbs": False,
    "skipDemultiplex": False,
    "useKallisto": False,
    "usePanel": False,
    "useDda": False,
    "useRescore": False,
    "deleteFastqs": True,
    "runDmpSelection": False,
    "runGeneFeaturecuts": False,
    "runBiomarkerFilter": False,
    "runGeneFeatureSelect": False,
    "runProgressionAnalysis": False,
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
    "discovery_gene_featurecuts": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": True,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": True,
        "stabilityGeneBiomarkerFilterEnabled": False,
    },
    "structural_features": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": True,
    },
    "staged_ovr_mc": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": True,
        "runProgressionAnalysis": True,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": True,
    },
    "staged_full_lifecycle": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": True,
        "runProgressionAnalysis": True,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": True,
    },
    "mc_gene_fc": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": True,
        "stabilityFeaturecutsEnabled": False,
        "stabilityGeneFeaturecutsEnabled": True,
    },
    "mc_dmp_gene_fc": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": True,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": True,
    },
    # SaMD lifecycle ladder (healthy vs disease; partitions on study manifest)
    "samd_research": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": True,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": True,
    },
    "samd_holdout_enrichment": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": True,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": True,
    },
    "samd_pivotal": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": True,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": True,
    },
    # Deprecated alias — use mc_dmp_gene_fc
    "buffy_mc_gene_fc": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": True,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": True,
    },
    # Research stability profiles (process-agnostic; study facts live in project.json)
    "mc_dmp": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": False,
        "stabilityGeneFeaturecutsEnabled": False,
        "stabilityGeneBiomarkerFilterEnabled": False,
    },
    "mc_dmp_fc": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": False,
    },
    "mc_gene": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": False,
        "stabilityGeneFeaturecutsEnabled": False,
        "stabilityGeneBiomarkerFilterEnabled": False,
    },
    # Statistical-mode profiles (deprecated names; aliases resolve to mc_* above)
    "mc_dmp_discovery": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": False,
        "stabilityGeneFeaturecutsEnabled": False,
        "stabilityGeneBiomarkerFilterEnabled": False,
    },
    "mc_dmp_featurecuts": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": False,
    },
    "mc_gene_mapper": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": False,
        "stabilityGeneFeaturecutsEnabled": False,
        "stabilityGeneBiomarkerFilterEnabled": False,
    },
    "mc_gene_featurecuts": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": True,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": False,
        "stabilityGeneFeaturecutsEnabled": True,
        "stabilityGeneBiomarkerFilterEnabled": False,
    },
    "mc_two_phase_dmp_then_gene": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": True,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": False,
        "stabilityGeneFeaturecutsEnabled": True,
    },
    "phase_a_dmp_stability": {
        "runDmpSelection": True,
        "runGeneFeaturecuts": False,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": True,
        "stabilityGeneFeaturecutsEnabled": False,
    },
    "phase_b_gene_from_stable_dmps": {
        "runDmpSelection": False,
        "runGeneFeaturecuts": True,
        "runBiomarkerFilter": False,
        "runGeneFeatureSelect": False,
        "stabilityFeaturecutsEnabled": False,
        "stabilityGeneFeaturecutsEnabled": True,
    },
}


def _derive_scope_from_modeling_modes(validation: Mapping[str, Any]) -> Dict[str, bool]:
    """Map dmp_modeling_mode / gene_modeling_mode to pipeline IF booleans."""
    dmp_mode = str(validation.get("dmp_modeling_mode") or "").strip().lower()
    gene_mode = str(validation.get("gene_modeling_mode") or "").strip().lower()
    if not dmp_mode and bool(validation.get("stability_featurecuts_enabled")):
        dmp_mode = "featurecuts"
    if not dmp_mode:
        dmp_mode = "raw_pool"
    if not gene_mode:
        if bool(validation.get("stability_gene_featurecuts_enabled")):
            gene_mode = "featurecuts"
        elif validation.get("stability_gene_recurrence_source") == "mapper":
            gene_mode = "mapper_ranked"
        else:
            gene_mode = "none"
    run_dmp = dmp_mode == "featurecuts"
    run_gene_fc = gene_mode in ("featurecuts", "from_stable_dmp_panel")
    return {
        "runDmpSelection": run_dmp,
        "runGeneFeaturecuts": run_gene_fc,
        "stabilityFeaturecutsEnabled": dmp_mode == "featurecuts",
        "stabilityGeneFeaturecutsEnabled": run_gene_fc,
    }


def load_profile_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mode_search_dirs() -> list[Path]:
    """Directories that may contain ``modes/<id>.mode.json`` (honors METHYL_PROFILE_DIR)."""
    from methyl_utils.profile_paths import profile_search_dirs

    dirs: list[Path] = []
    # Sibling of this module (repo checkout or runtime-bundle/domain on sys.path)
    dirs.append(Path(__file__).resolve().parent / "profiles")
    for d in profile_search_dirs():
        dirs.append(d)
    # Deduplicate while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for d in dirs:
        resolved = d.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def load_mode_overlay(mode_id: str) -> Dict[str, Any]:
    """Load a samd_research modeling-mode overlay (``…/profiles/modes/<id>.mode.json``)."""
    candidates: list[Path] = []
    for profiles_dir in _mode_search_dirs():
        path = profiles_dir / "modes" / f"{mode_id}.mode.json"
        candidates.append(path)
        if path.is_file():
            return load_profile_file(path)
    known: list[str] = []
    for profiles_dir in _mode_search_dirs():
        modes_dir = profiles_dir / "modes"
        if modes_dir.is_dir():
            known.extend(p.stem for p in modes_dir.glob("*.mode.json"))
    known_u = sorted(set(known))
    raise FileNotFoundError(
        f"Unknown research mode {mode_id!r} (expected one of {known_u}; "
        f"searched: {', '.join(str(c) for c in candidates)})"
    )


def load_samd_research_with_mode(
    mode_id: str,
    *,
    pipeline_profile: str = "samd_research",
) -> Dict[str, Any]:
    """Merge ``samd_research.profile.json`` with a named mode overlay.

    Mode overlays carry statistical axis knobs only. Legacy ``mc_*`` alias folds
    additionally reset SaMD research lifecycle flags (early-stop, holdout eval,
    regulatory stubs) so historical ``mc_*`` behavior is preserved. Prefer
    ``pipelineProfile: samd_research`` + ``researchMode`` so early-stop stays on.
    """
    from methyl_utils.profile_paths import resolve_profile_path

    base = load_profile_file(resolve_profile_path("samd_research"))
    merged = _deep_merge(base, load_mode_overlay(mode_id))
    merged["pipelineProfile"] = pipeline_profile
    merged["researchMode"] = mode_id
    if pipeline_profile in _SAMD_RESEARCH_MODES:
        # Deprecated mc_* path: do not inherit samd_research early-stop / claim shell.
        ac = dict(merged.get("actionConfig") or {})
        val = dict(ac.get("validation") or {})
        val["stability_early_stop_enabled"] = False
        val["holdout_eval"] = False
        val["require_biological_review_for_model"] = False
        val["biological_review_confirmed"] = False
        val["regulatory"] = {
            "stage": "feasibility",
            "intended_use_summary": (
                f"Deprecated profile alias {pipeline_profile} folded into "
                f"samd_research mode {mode_id}."
            ),
            "allow_clinical_performance_claims": False,
            "claim_boundary": (
                "Research axis via samd_research mode overlay; not pivotal claims."
            ),
            "primary_analyte": "buffy_coat",
        }
        val["validation_partitions"] = {
            "development_train": [],
            "internal_validation": [],
            "locked_test": [],
            "pivotal_validation": [],
            "post_market_monitoring": [],
            "independence_keys": ["sample_id", "patient_id", "site_id", "batch"],
        }
        ac["validation"] = val
        merged["actionConfig"] = ac
    return merged


def load_profile(name_or_path: str | Path) -> Dict[str, Any]:
    from methyl_utils.profile_paths import resolve_profile_path

    p = Path(name_or_path)
    if p.is_file():
        data = load_profile_file(p)
        key = str(data.get("pipelineProfile") or "")
        if key in _PROFILE_ALIASES:
            key = _PROFILE_ALIASES[key]
        if key in _SAMD_RESEARCH_MODES:
            return load_samd_research_with_mode(
                _SAMD_RESEARCH_MODES[key],
                pipeline_profile=key,
            )
        if key == "samd_research":
            data.setdefault("researchMode", "dual_fc")
        return data

    key = str(name_or_path)
    if key in _PROFILE_ALIASES:
        return load_profile(_PROFILE_ALIASES[key])
    if key in _SAMD_RESEARCH_MODES:
        return load_samd_research_with_mode(
            _SAMD_RESEARCH_MODES[key],
            pipeline_profile=key,
        )
    if key in _RESEARCH_MODE_IDS:
        # Allow pipelineProfile / name = mode id → samd_research + overlay.
        return load_samd_research_with_mode(key, pipeline_profile="samd_research")
    try:
        data = load_profile_file(resolve_profile_path(key))
    except FileNotFoundError:
        if key in PROFILE_PRESETS:
            return {"pipelineProfile": key, **PROFILE_PRESETS[key]}
        raise FileNotFoundError(f"Unknown pipeline profile: {name_or_path!r}") from None
    if key == "samd_research":
        data.setdefault("researchMode", "dual_fc")
    return data


def profile_action_config(profile: Mapping[str, Any]) -> Dict[str, Any]:
    ac = profile.get("actionConfig") or profile.get("step_config_overrides") or {}
    return dict(ac) if isinstance(ac, dict) else {}


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
    action_config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Flatten validation / gene_selection / dmp_selection keys into IF-friendly scope booleans."""
    out = dict(context)
    ac = dict(action_config or {})
    validation = dict(ac.get("validation") or {})
    gene_sel = dict(ac.get("gene_selection") or {})
    dmp_sel = dict(ac.get("dmp_selection") or {})

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
    out.setdefault(
        "runProgressionAnalysis",
        _flag("runProgressionAnalysis", "enabled")
        or bool(ac.get("progression", {}).get("enabled") if isinstance(ac.get("progression"), dict) else False),
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

    mode_flags = _derive_scope_from_modeling_modes({**validation, **gene_sel, **dmp_sel})
    if validation.get("dmp_modeling_mode") or validation.get("gene_modeling_mode"):
        for key, val in mode_flags.items():
            out[key] = bool(val)


    # Methylation library protocol (WGBS vs epi-GBS). Keeps Parabricks SamplePrep
    # isolated from the epi-GBS DomainProgram (sample_prep_epigbs.program.json).
    sample_prep_cfg = dict(ac.get("sample_prep") or {})
    demux_cfg = dict(ac.get("demultiplex") or {})
    library_protocol = out.get("libraryProtocol")
    if library_protocol in (None, ""):
        library_protocol = sample_prep_cfg.get("library_protocol")
    if library_protocol in (None, ""):
        library_protocol = "wgbs_linear"
    proto = str(library_protocol).strip().lower().replace("-", "_")
    if proto in {"wgbs", "linear", "wgbslinear"}:
        proto = "wgbs_linear"
    elif proto in {"pangenome", "wgbs_pangenome", "wgbspangenome"}:
        proto = "wgbs_pangenome"
    elif proto in {"epi_gbs", "epigbs", "epi_gbs_methylation"}:
        proto = "epi_gbs"
    out["libraryProtocol"] = proto
    if "useEpiGbs" in out:
        out["useEpiGbs"] = bool(out["useEpiGbs"])
    else:
        out.setdefault("useEpiGbs", proto == "epi_gbs")
    if "skipDemultiplex" in out:
        out["skipDemultiplex"] = bool(out["skipDemultiplex"])
    else:
        skip_demux = demux_cfg.get("skip")
        if skip_demux is None:
            skip_demux = sample_prep_cfg.get("skip_demultiplex")
        out.setdefault("skipDemultiplex", bool(skip_demux))

    parabricks_cfg = dict(ac.get("parabricks") or {})
    alignment_mode = out.get("alignmentMode")
    if alignment_mode in (None, ""):
        alignment_mode = parabricks_cfg.get("alignment_mode")
    if alignment_mode in (None, ""):
        # Derive WGBS alignment mode from libraryProtocol when unset.
        if proto == "wgbs_pangenome":
            alignment_mode = "pangenome"
        else:
            alignment_mode = "linear"
    out["alignmentMode"] = str(alignment_mode)
    if "usePangenome" in out:
        out["usePangenome"] = bool(out["usePangenome"])
    else:
        out.setdefault(
            "usePangenome",
            str(alignment_mode).strip().lower() == "pangenome" or proto == "wgbs_pangenome",
        )

    # RNA-Seq quantifier selection, parallel to alignment_mode/usePangenome.
    rna_align_cfg = dict(ac.get("rna_align") or {})
    quant_mode = out.get("quantMode")
    if quant_mode in (None, ""):
        quant_mode = rna_align_cfg.get("quant_mode")
    if quant_mode in (None, ""):
        quant_mode = "star"
    out["quantMode"] = str(quant_mode)
    if "useKallisto" in out:
        out["useKallisto"] = bool(out["useKallisto"])
    else:
        out.setdefault(
            "useKallisto",
            str(quant_mode).strip().lower() == "kallisto",
        )

    # Proteomics ingest selection: ingest_mode (dia | panel) -> usePanel; rescore -> useRescore.
    prot_cfg = dict(ac.get("proteomics_quant") or {})
    ingest_mode = out.get("ingestMode") or prot_cfg.get("ingest_mode") or "dia"
    out["ingestMode"] = str(ingest_mode)
    if "usePanel" in out:
        out["usePanel"] = bool(out["usePanel"])
    else:
        out.setdefault("usePanel", str(ingest_mode).strip().lower() == "panel")
    if "useDda" in out:
        out["useDda"] = bool(out["useDda"])
    else:
        out.setdefault("useDda", str(ingest_mode).strip().lower() == "dda")
    if "useRescore" in out:
        out["useRescore"] = bool(out["useRescore"])
    else:
        out.setdefault("useRescore", bool(prot_cfg.get("rescore", False)))

    sample_prep_cfg = dict(ac.get("sample_prep") or {})
    if "deleteFastqs" in out:
        out["deleteFastqs"] = bool(out["deleteFastqs"])
    else:
        raw_del = sample_prep_cfg.get("delete_fastqs", sample_prep_cfg.get("deleteFastqs"))
        if raw_del is None:
            out.setdefault("deleteFastqs", True)
        else:
            out["deleteFastqs"] = bool(raw_del)

    stable_csv = out.get("stableDmpCsv") or validation.get("freeze_stable_dmp_csv")
    if stable_csv and out.get("pipelineProfile") in (
        "phase_b_gene_from_stable_dmps",
        "mc_two_phase_dmp_then_gene",
    ):
        ac = dict(out.get("actionConfig") or {})
        val = dict(ac.get("validation") or {})
        val.setdefault("freeze_stable_dmp_csv", str(stable_csv))
        val.setdefault("gene_modeling_mode", "from_stable_dmp_panel")
        val.setdefault("gene_featurecuts_loci_source", "stable_panel")
        val.setdefault("dmp_modeling_mode", "stable_panel")
        ac["validation"] = val
        mapper = dict(ac.get("mapper") or {})
        mapper.setdefault("csv_pattern", "stable_dmps*.csv")
        ac["mapper"] = mapper
        out["actionConfig"] = ac

    return out


def apply_pipeline_profile(
    context: Dict[str, Any],
    profile: Mapping[str, Any],
    *,
    action_config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge a profile dict into workflow instance context (flags + actionConfig)."""
    out = dict(context)
    name = profile.get("pipelineProfile")
    # Prefer context researchMode when applying samd_research (mode overlay path).
    context_mode = out.get("researchMode")
    if (
        name == "samd_research"
        and context_mode
        and str(context_mode) != str(profile.get("researchMode") or "dual_fc")
    ):
        profile = load_samd_research_with_mode(
            str(context_mode),
            pipeline_profile="samd_research",
        )
        name = profile.get("pipelineProfile")
    if name:
        out["pipelineProfile"] = name
    preset = PROFILE_PRESETS.get(str(name), {}) if name else {}
    for key, val in {**preset, **profile}.items():
        if key in ("pipelineProfile", "actionConfig", "step_config_overrides"):
            continue
        if key in _STRING_SCOPE_KEYS and val is not None:
            out.setdefault(key, val)
            continue
        if isinstance(val, bool) or key in PIPELINE_FLAG_DEFAULTS:
            out[key] = bool(val)
    if profile.get("researchMode") and "researchMode" not in out:
        out["researchMode"] = profile["researchMode"]
    profile_ac = profile_action_config(profile)
    if profile_ac:
        # Instance/context actionConfig is the higher layer (see layer-model precedence):
        # profile provides the base, context overlays win — including explicit JSON nulls
        # that clear a profile knob (e.g. stability_min_balanced_accuracy: null).
        existing = dict(out.get("actionConfig") or {})
        out["actionConfig"] = _deep_merge(dict(profile_ac), existing)

    effective: Dict[str, Any] = dict(action_config or {})
    ctx_ac = out.get("actionConfig")
    if isinstance(ctx_ac, dict):
        effective = _deep_merge(effective, ctx_ac)

    return seed_pipeline_scope_flags(out, action_config=effective)


def apply_profile_by_name(context: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
    return apply_pipeline_profile(context, load_profile(profile_name))
