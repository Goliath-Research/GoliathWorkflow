"""Study Guardrails (next run) overlay: typed editor surface + sparse diff.

Operators edit the **effective** next-run document (site → profile → procedure
→ existing study overlay). The stored ``cfg.study.document_json.actionConfig``
slice is only the **diff** against inherited layers:

* omit a key — inherit
* JSON ``null`` — delete that inherited leaf

Do **not** bind ``AlignmentQCConfig`` / ``ExtractionQCConfig`` as the editor
schema: those require workflow identity (``sample_paths``, ``output_dir``) and
bake numeric defaults that would pin the whole published window into the study.

The committed JSON Schema is ``schemas/config/study_action_config_overlay.schema.json``.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Literal, Mapping, Optional, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

from .action_config_resolver import deep_merge

SCHEMA_ID = "study_action_config_overlay"
SCHEMA_FILENAME = "study_action_config_overlay.schema.json"
GUARDRAIL_ACTION_KEYS = ("alignment_qc", "extraction_qc")

_INHERIT = (
    "Omit to inherit site/profile/procedure. JSON null clears the inherited leaf. "
    "Operator-set on Studies → Guardrails (next run)."
)


class CycleScreeningOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: Optional[bool] = Field(default=None, description=_INHERIT)
    read_length: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    r2_start_window_cycles: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    recovery_cycles: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    r2_quality_threshold: Optional[float] = Field(default=None, description=_INHERIT)
    max_trim_bases: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    multi_region_min_separate_dips: Optional[int] = Field(default=None, ge=2, description=_INHERIT)
    read_edge_window: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    broad_bad_cycle_count: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    localized_max_span: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    remediate_without_cycles: Optional[bool] = Field(default=None, description=_INHERIT)
    fallback_trim_front: Optional[int] = Field(default=None, ge=0, description=_INHERIT)
    fallback_trim_tail: Optional[int] = Field(default=None, ge=0, description=_INHERIT)


class CoreGuardrailsOverlay(BaseModel):
    """Sparse overlay of WGBS core thresholds. No published-window defaults."""

    model_config = ConfigDict(extra="forbid")

    min_pf_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0, description=_INHERIT)
    min_q30_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0, description=_INHERIT)
    min_mean_quality: Optional[float] = Field(default=None, ge=0.0, description=_INHERIT)
    min_quality_post20: Optional[float] = Field(default=None, ge=0.0, description=_INHERIT)
    max_at_dropout: Optional[float] = Field(default=None, ge=0.0, description=_INHERIT)
    max_gc_dropout: Optional[float] = Field(default=None, ge=0.0, description=_INHERIT)
    median_insert_min_bp: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    median_insert_max_bp: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    max_deamination_qscore: Optional[int] = Field(default=None, ge=0, description=_INHERIT)
    min_oxog_qscore: Optional[int] = Field(default=None, ge=0, description=_INHERIT)


class OptionalGuardrailsOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duplication_rate_max: Optional[float] = Field(default=None, ge=0.0, le=1.0, description=_INHERIT)
    min_pf_reads: Optional[int] = Field(default=None, ge=1, description=_INHERIT)


class AlignmentGuardrailsOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: Optional[bool] = Field(default=None, description=_INHERIT)
    min_mapping_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description=_INHERIT)
    wgbs_min_mapped_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description=_INHERIT)
    max_secondary_supplementary_rate: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description=_INHERIT
    )
    min_gc_coverage_uniformity: Optional[float] = Field(default=None, ge=0.0, description=_INHERIT)
    flagstat_enabled: Optional[bool] = Field(default=None, description=_INHERIT)
    min_properly_paired_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description=_INHERIT)
    max_supplementary_rate_flagstat: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description=_INHERIT
    )


class BisulfiteConversionOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: Optional[bool] = Field(default=None, description=_INHERIT)
    source: Optional[Literal["sidecar", "deamination_proxy", "auto"]] = Field(
        default=None, description=_INHERIT
    )
    sidecar_filename: Optional[str] = Field(default=None, description=_INHERIT)
    min_conversion_rate_pct: Optional[float] = Field(
        default=None, ge=0.0, le=100.0, description=_INHERIT
    )
    max_non_cpg_methylation_pct: Optional[float] = Field(
        default=None, ge=0.0, le=100.0, description=_INHERIT
    )
    max_deamination_qscore_proxy: Optional[int] = Field(default=None, ge=0, description=_INHERIT)


class FragmentomicsOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: Optional[bool] = Field(default=None, description=_INHERIT)
    profile: Optional[Literal["off", "cfdna", "wgbs"]] = Field(default=None, description=_INHERIT)
    short_fragment_max_bp: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    long_fragment_min_bp: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    nucleosome_peak_bp_min: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    nucleosome_peak_bp_max: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    median_insert_min_bp: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    median_insert_max_bp: Optional[int] = Field(default=None, ge=1, description=_INHERIT)
    max_short_fragment_fraction: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description=_INHERIT
    )


class AlignmentQcOverlay(BaseModel):
    """Operator-tunable ``alignment_qc`` slice. No sample paths or output dir."""

    model_config = ConfigDict(extra="forbid")

    auto_profile_from_analyte: Optional[bool] = Field(default=None, description=_INHERIT)
    fragmentomics: Optional[FragmentomicsOverlay] = Field(default=None, description=_INHERIT)
    bisulfite_conversion: Optional[BisulfiteConversionOverlay] = Field(
        default=None, description=_INHERIT
    )
    cycle_screening: Optional[CycleScreeningOverlay] = Field(default=None, description=_INHERIT)
    core_guardrails: Optional[CoreGuardrailsOverlay] = Field(default=None, description=_INHERIT)
    optional_guardrails: Optional[OptionalGuardrailsOverlay] = Field(
        default=None, description=_INHERIT
    )
    alignment_guardrails: Optional[AlignmentGuardrailsOverlay] = Field(
        default=None, description=_INHERIT
    )


class ExtractionQcGuardrailOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_cpg_weighted_mean_coverage: Optional[float] = Field(default=None, ge=0.0, description=_INHERIT)
    max_chh_methylation_level: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description=_INHERIT
    )
    max_chg_methylation_level: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description=_INHERIT
    )
    min_autosomal_coverage_uniformity_ratio: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description=_INHERIT
    )
    max_discard_fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0, description=_INHERIT)


class ExtractionQcOverlay(BaseModel):
    """Operator-tunable ``extraction_qc`` slice. No sample paths."""

    model_config = ConfigDict(extra="forbid")

    guardrails: Optional[ExtractionQcGuardrailOverlay] = Field(default=None, description=_INHERIT)
    expected_chromosomes: Optional[List[str]] = Field(default=None, description=_INHERIT)


class StudyActionConfigOverlay(BaseModel):
    """JSON Schema bind target for Studies → Guardrails (next run).

    The property grid binds this schema to the **effective** document (inherited
    values filled in). Persist only ``sparse_overlay_diff(inherited, edited)``.
    """

    model_config = ConfigDict(extra="forbid")

    alignment_qc: Optional[AlignmentQcOverlay] = Field(
        default=None,
        description="Alignment QC guardrails overlay. Omit the object to inherit the whole slice.",
    )
    extraction_qc: Optional[ExtractionQcOverlay] = Field(
        default=None,
        description="Extraction QC guardrails overlay. Omit the object to inherit the whole slice.",
    )


def _nested_model(annotation: Any) -> type[BaseModel] | None:
    origin = get_origin(annotation)
    if origin is Union:
        candidates = [a for a in get_args(annotation) if a is not type(None)]
        if len(candidates) == 1:
            annotation = candidates[0]
        else:
            return None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def take_known_fields(model: type[BaseModel], data: Any) -> Any:
    """Keep only fields declared on ``model`` (recursive). Preserves JSON null."""
    if data is None or not isinstance(data, Mapping):
        return data
    out: Dict[str, Any] = {}
    for name, field in model.model_fields.items():
        if name not in data:
            continue
        value = data[name]
        nested = _nested_model(field.annotation)
        if nested is not None and isinstance(value, Mapping):
            out[name] = take_known_fields(nested, value)
        else:
            out[name] = copy.deepcopy(value)
    return out


def slice_guardrails(action_config: Mapping[str, Any] | None) -> Dict[str, Any]:
    """Project an actionConfig map onto the Guardrails editor keys."""
    raw = dict(action_config or {})
    sliced = {key: raw[key] for key in GUARDRAIL_ACTION_KEYS if key in raw}
    known = take_known_fields(StudyActionConfigOverlay, sliced)
    return known if isinstance(known, dict) else {}


_MISSING = object()


def sparse_overlay_diff(
    baseline: Mapping[str, Any] | None,
    edited: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    """Return the overlay such that ``deep_merge(baseline, overlay)`` equals ``edited``.

    Equal values are omitted. A key present on ``baseline`` but missing from
    ``edited`` becomes JSON ``null`` (delete leaf). Nested objects recurse.
    Lists and scalars replace wholesale (same as ``deep_merge``).
    """
    base = dict(baseline or {})
    edit = dict(edited or {})
    out: Dict[str, Any] = {}
    for key, edited_val in edit.items():
        if edited_val is None:
            if key in base:
                out[key] = None
            continue
        base_val = base.get(key, _MISSING)
        if isinstance(edited_val, dict) and isinstance(base_val, dict):
            child = sparse_overlay_diff(base_val, edited_val)
            if child:
                out[key] = child
        elif base_val != edited_val:
            out[key] = copy.deepcopy(edited_val)
    for key in base:
        if key not in edit:
            out[key] = None
    return out


def compose_study_guardrails(
    *,
    site_action_config: Mapping[str, Any] | None = None,
    profile_action_config: Mapping[str, Any] | None = None,
    procedure_action_config: Mapping[str, Any] | None = None,
    study_overlay: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the Guardrails editor payload (later layer wins).

    Merge order matches instance bake: site → profile → procedure → study overlay.
    """
    inherited: Dict[str, Any] = {}
    for layer in (site_action_config, profile_action_config, procedure_action_config):
        inherited = deep_merge(inherited, slice_guardrails(layer))
    overlay = slice_guardrails(study_overlay)
    effective = deep_merge(inherited, overlay)
    return {
        "schema_id": SCHEMA_ID,
        "inherited": inherited,
        "overlay": overlay,
        "effective": effective,
    }


def overlay_from_edited_effective(
    *,
    inherited: Mapping[str, Any],
    edited_effective: Mapping[str, Any],
    existing_action_config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Validate the edited working document and return the full study actionConfig.

    Guardrail keys are replaced by the computed sparse diff. Every other
    ``actionConfig`` key (HPO ``validation``, mapper, …) is preserved.
    """
    edited = slice_guardrails(edited_effective)
    StudyActionConfigOverlay.model_validate(edited)
    guardrail_overlay = sparse_overlay_diff(inherited, edited)
    StudyActionConfigOverlay.model_validate(guardrail_overlay)

    merged = dict(existing_action_config or {})
    for key in GUARDRAIL_ACTION_KEYS:
        merged.pop(key, None)
    for key, value in guardrail_overlay.items():
        if value is None:
            continue
        merged[key] = value
    return merged
