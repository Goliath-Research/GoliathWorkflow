"""CLI argv builder for pipeline.detector (methyl-detector step-override contract)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import CliAction, HandlerResult

# methyl-detector accepts --project, --group, --step-override, --centroid1-dir, --centroid2-dir.
# Per-chromosome scope uses step-override JSON (chromosome, contexts, fixed_dmp_panel, output_dir).
DETECTOR_ARGV_MAP: Dict[str, str] = {
    "project": "--project",
    "projectPath": "--project",
    "project_path": "--project",
    "group": "--group",
    "centroid1Dir": "--centroid1-dir",
    "centroid2Dir": "--centroid2-dir",
    "stepOverride": "--step-override",
}


def merge_detector_step_override(input_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fold workflow scope fields into a methyl-detector step-override object."""
    raw = input_json.get("stepOverride")
    merged: Dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}

    chromosome = input_json.get("chromosome")
    if chromosome not in (None, ""):
        merged["chromosome"] = chromosome

    context = input_json.get("context")
    if context not in (None, ""):
        if isinstance(context, list):
            merged["contexts"] = [str(c) for c in context if str(c).strip()]
        else:
            merged["contexts"] = [str(context)]

    panel = input_json.get("fixedDmpPanel")
    if panel not in (None, ""):
        merged["fixed_dmp_panel"] = str(panel)

    output_dir = input_json.get("outputDir")
    if output_dir not in (None, ""):
        merged["output_dir"] = str(output_dir)

    add_samples = input_json.get("addSamples")
    remove_samples = input_json.get("removeSamples")
    if add_samples is not None or remove_samples is not None:
        base_cfg = dict(merged.get("base_config") or {})
        if add_samples is not None:
            base_cfg["add_samples"] = list(add_samples)
        if remove_samples is not None:
            base_cfg["remove_samples"] = list(remove_samples)
        merged["base_config"] = base_cfg

    return merged or None


def resolve_detector_group(input_json: Dict[str, Any]) -> Optional[str]:
    """Map workflow comparison label to methyl-detector --group."""
    group = input_json.get("group")
    if group not in (None, ""):
        return str(group)
    comparison = input_json.get("comparison")
    if comparison not in (None, ""):
        return str(comparison)
    return None


class DetectorCliAction(CliAction):
    """Build methyl-detector argv without unsupported per-chromosome CLI flags."""

    def build_argv(self, input_json: Dict[str, Any]) -> List[str]:
        payload: Dict[str, Any] = dict(input_json)
        override = merge_detector_step_override(payload)
        if override is not None:
            payload["stepOverride"] = override
        group = resolve_detector_group(payload)
        if group is not None:
            payload["group"] = group
        for drop_key in (
            "chromosome",
            "context",
            "comparison",
            "fixedDmpPanel",
            "outputDir",
            "addSamples",
            "removeSamples",
        ):
            payload.pop(drop_key, None)
        return super().build_argv(payload)

    def execute(self, input_json: Dict[str, Any]) -> HandlerResult:
        return super().execute(input_json)
