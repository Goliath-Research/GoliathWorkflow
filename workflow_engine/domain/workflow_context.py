"""
WorkflowContext contract: how instance parameters become per-action input_json.

Parameter derivation lives in planners + SQL engine (templates, scope, bindings).
Workers receive fully resolved payloads from the DB read-path when instances are
configured with ``finalize_instance_context`` (``resolvedConfig__*`` scope vars).
This module supports planners, admin CLI, tests, and ``LocalWorkflowEngine``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

_PLACEHOLDER_RE = re.compile(r"^\$\{var\.([^}]+)\}$")


class InstanceContext(BaseModel):
    """Minimal or enriched payload for workflow_instance.context_json."""

    model_config = ConfigDict(extra="allow")

    projectPath: str
    project: Optional[Dict[str, Any]] = None
    iterations: Optional[List[Dict[str, Any]]] = None
    samples: Optional[List[Dict[str, Any]]] = None
    comparisons: Optional[List[Dict[str, Any]]] = None
    chromosomes: Optional[List[str]] = None
    contexts: Optional[List[str]] = None
    centroid1Dir: Optional[str] = None


class ResolvedScope(BaseModel):
    """Read-only scope snapshot for tests and planners."""

    vars: Dict[str, Any] = Field(default_factory=dict)


class ActionInputSpec(BaseModel):
    """Expected resolved keys for one ACTION (from catalog + task schema)."""

    action_name: str
    required_keys: List[str]
    optional_keys: List[str] = Field(default_factory=list)


def _resolve_project_path(context: Mapping[str, Any]) -> Path:
    raw = context.get("projectPath") or context.get("project_path")
    if not raw:
        raise ValueError("context_json missing projectPath")
    path = Path(str(raw)).expanduser().resolve()
    if path.is_dir():
        candidate = path / "project.json"
        if candidate.is_file():
            return candidate
    if path.is_file():
        return path
    raise FileNotFoundError(f"Could not resolve project.json from projectPath={raw!r}")


def enrich_comparisons_from_project(project_path: Path) -> List[Dict[str, Any]]:
    """Build comparison objects with output path fields for workflow scope."""
    from methyl_utils import load_project

    project = load_project(str(project_path))
    comparisons = project.get_comparisons()
    if not comparisons:
        return []

    enriched: List[Dict[str, Any]] = []
    for cmp in comparisons:
        control = cmp.control_group
        disease = cmp.disease_group
        label = cmp.comparison_label or disease or f"{control}_vs_{disease}"
        enriched.append(
            {
                "label": label,
                "control_group": control,
                "disease_group": disease,
                "comparisonLabel": label,
                "centroid2Dir": project.get_centroid_dir("disease", disease),
                "detectOutDir": project.get_detection_output_dir(control, disease),
            }
        )
    return enriched


def enrich_instance_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expand minimal ``{ projectPath }`` into engine-ready context_json.

    Adds comparisons (with path fields), chromosomes, contexts, and shared
    ``centroid1Dir`` when absent. Safe to call on already-enriched payloads.
    """
    out = dict(context)
    project_path = _resolve_project_path(out)

    from methyl_utils import load_project
    from methyl_utils.action_config_resolver import load_site_manifest
    from pipeline_profiles import (
        PIPELINE_FLAG_DEFAULTS,
        apply_pipeline_profile,
        load_profile,
        profile_action_config,
        seed_pipeline_scope_flags,
    )

    project = load_project(str(project_path))

    if not out.get("comparisons"):
        out["comparisons"] = enrich_comparisons_from_project(project_path)

    if not out.get("chromosomes"):
        out["chromosomes"] = list(project.chromosomes or [])

    if not out.get("contexts"):
        out["contexts"] = list(getattr(project, "contexts", None) or ["CG"])

    if not out.get("centroid1Dir") and out.get("comparisons"):
        first = out["comparisons"][0]
        control = first.get("control_group") or first.get("group1Label")
        if control:
            out["centroid1Dir"] = project.get_centroid_dir("control", str(control))

    if not out.get("groups"):
        resolved = project.get_resolved_groups()
        out["groups"] = [{"label": label} for label, _ in resolved]

    if not out.get("siteConfig"):
        site_path = out.get("siteConfigPath")
        out["siteConfig"] = load_site_manifest(site_path) if site_path else load_site_manifest()

    if not out.get("regulatory"):
        out["regulatory"] = project.get_regulatory_config()

    profile_name = out.get("pipelineProfile")
    profile_file = out.get("profilePath")
    if profile_file or profile_name:
        profile = load_profile(profile_file or profile_name)
        out = apply_pipeline_profile(out, profile)
    elif out.get("actionConfig"):
        out = seed_pipeline_scope_flags(out, action_config=out.get("actionConfig"))
    elif any(k in out for k in PIPELINE_FLAG_DEFAULTS):
        out = seed_pipeline_scope_flags(out, action_config=profile_action_config(out))

    return out


def _lookup_scope_path(scope: Mapping[str, Any], path: str) -> Any:
    """Resolve dotted scope paths such as ``iteration.runDir``."""
    cur: Any = scope
    for part in path.split("."):
        if isinstance(cur, Mapping) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def _resolve_template_value(value: Any, scope: Mapping[str, Any], *, missing: str = "error") -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {"ref"} and isinstance(value.get("ref"), str):
            try:
                return _lookup_scope_path(scope, str(value["ref"]))
            except KeyError:
                if missing == "none":
                    return None
                raise
        return {k: _resolve_template_value(v, scope, missing=missing) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_template_value(v, scope, missing=missing) for v in value]
    return resolve_placeholder(value, scope, missing=missing)


def resolve_placeholder(
    value: Any, scope: Mapping[str, Any], *, missing: str = "error"
) -> Any:
    """Resolve ``${var.name}`` placeholders (Python mirror of SQL read-path)."""
    if isinstance(value, dict):
        return {k: resolve_placeholder(v, scope, missing=missing) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_placeholder(v, scope, missing=missing) for v in value]
    if not isinstance(value, str):
        return value
    m = _PLACEHOLDER_RE.match(value.strip())
    if not m:
        return value
    key = m.group(1)
    if key in scope:
        return scope[key]
    try:
        return _lookup_scope_path(scope, key)
    except KeyError:
        if missing == "none":
            return None
        raise KeyError(f"unresolved scope variable: {key}") from None


def resolve_input_json_from_template(
    template: Mapping[str, Any], scope: Mapping[str, Any]
) -> Dict[str, Any]:
    """Resolve an action input_template against a flat scope dict (for tests)."""
    resolved = _resolve_template_value(dict(template), scope, missing="none")
    if not isinstance(resolved, dict):
        return {}
    return {k: v for k, v in resolved.items() if v is not None}


def list_unresolved_placeholders(value: Any) -> List[str]:
    """Return placeholder var names still present in a nested structure."""
    found: Set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, str):
            m = _PLACEHOLDER_RE.match(obj.strip())
            if m:
                found.add(m.group(1))

    walk(value)
    return sorted(found)


def action_input_spec_for(action_name: str) -> Optional[ActionInputSpec]:
    """Load required keys from the action catalog entry."""
    import sys
    from pathlib import Path as _Path

    workers = _Path(__file__).resolve().parents[2] / "workers"
    if str(workers) not in sys.path:
        sys.path.insert(0, str(workers))

    from methyl_worker.action_catalog import find_catalog_entry

    entry = find_catalog_entry(action_name)
    if entry is None:
        return None

    optional = {
        "outputDir",
        "centroid1Dir",
        "centroid2Dir",
        "centroidSeedDir",
        "taskConfig",
        "phase",
        "runId",
        "addSamples",
        "removeSamples",
        "stepOverride",
        "comparison",
        "fixedDmpPanel",
    }
    required = ["tool"]
    if entry.action_config_key:
        required.extend(["project", "projectPath"])
    required.extend(c for c in entry.context_vars if c not in optional)
    optional_keys = list(optional)
    return ActionInputSpec(
        action_name=action_name,
        required_keys=sorted(set(required)),
        optional_keys=optional,
    )


def resolved_config_scope_var_name(action_config_key: str) -> str:
    """Scope variable name for a pre-resolved actionConfig slice at instance start."""
    return f"resolvedConfig__{action_config_key}"


def build_resolved_config_scope_vars(context: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Resolve each actionConfig key once at instance configuration time.

    Flattened scope vars (``resolvedConfig__<key>``) are stored in context_json so
    the SQL engine can bind ``${var.resolvedConfig__*}`` in action input templates
    without gateway-side materialization at task claim.
    """
    import sys
    from pathlib import Path as _Path

    workers = _Path(__file__).resolve().parents[2] / "workers"
    if str(workers) not in sys.path:
        sys.path.insert(0, str(workers))

    from methyl_worker.action_catalog import ACTION_CATALOG
    from methyl_utils.action_config_resolver import resolve_action_config

    ac = context.get("actionConfig")
    profile_ac = dict(ac) if isinstance(ac, dict) else {}
    site = context.get("siteConfig") if isinstance(context.get("siteConfig"), dict) else {}
    reg = context.get("regulatory") if isinstance(context.get("regulatory"), dict) else {}

    keys: Set[str] = set(profile_ac.keys())
    for entry in ACTION_CATALOG:
        if entry.action_config_key:
            keys.add(entry.action_config_key)

    out: Dict[str, Any] = {}
    for key in sorted(keys):
        out[resolved_config_scope_var_name(key)] = resolve_action_config(
            key,
            site=site,
            profile_action_config=profile_ac,
            program_override=None,
            regulatory=reg,
        )
    return out


def finalize_instance_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich instance context and bake resolvedConfig scope vars for DB-backed runs.

    Call before ``create_workflow_instance`` when the workflow engine will resolve
    action input templates from scope (distributed path).
    """
    out = enrich_instance_context(context)
    out.update(build_resolved_config_scope_vars(out))
    return out


def materialize_action_input(
    input_json: Dict[str, Any],
    action_name: str,
    scope: Mapping[str, Any],
) -> Dict[str, Any]:
    """Inject resolvedConfig for workflow ACTION nodes when catalog defines action_config_key."""
    import sys
    from pathlib import Path as _Path

    workers = _Path(__file__).resolve().parents[2] / "workers"
    if str(workers) not in sys.path:
        sys.path.insert(0, str(workers))

    from methyl_worker.action_catalog import find_catalog_entry
    from methyl_utils.action_config_resolver import resolve_action_config

    entry = find_catalog_entry(action_name)
    if entry is None or not entry.action_config_key:
        return input_json

    out = dict(input_json)
    if isinstance(out.get("resolvedConfig"), dict):
        return out

    ac = scope.get("actionConfig")
    profile_ac = dict(ac) if isinstance(ac, dict) else {}
    site = scope.get("siteConfig") if isinstance(scope.get("siteConfig"), dict) else {}
    override = out.get("stepOverride") if isinstance(out.get("stepOverride"), dict) else None
    reg = scope.get("regulatory") if isinstance(scope.get("regulatory"), dict) else {}

    out["resolvedConfig"] = resolve_action_config(
        entry.action_config_key,
        site=site,
        profile_action_config=profile_ac,
        program_override=override,
        regulatory=reg,
    )
    return out


def validate_resolved_input_json(input_json: Mapping[str, Any], action_name: str) -> List[str]:
    """Return validation errors for a resolved worker payload."""
    errors: List[str] = []
    unresolved = list_unresolved_placeholders(dict(input_json))
    if unresolved:
        errors.append(f"unresolved placeholders: {', '.join(unresolved)}")

    spec = action_input_spec_for(action_name)
    if spec is None:
        return errors

    for key in spec.required_keys:
        if key == "projectPath":
            if not any(input_json.get(k) for k in ("project", "projectPath", "project_path")):
                errors.append("missing project or projectPath")
        elif input_json.get(key) in (None, ""):
            errors.append(f"missing required key: {key}")

    return errors


def instance_context_to_json(context: InstanceContext | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(context, InstanceContext):
        return context.model_dump(exclude_none=True)
    return dict(context)


def write_instance_context(path: Path, context: InstanceContext | Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = instance_context_to_json(context)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
