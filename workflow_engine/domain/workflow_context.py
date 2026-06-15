"""
WorkflowContext contract: how instance parameters become per-action input_json.

Parameter derivation lives in planners + SQL engine (templates, scope, bindings).
Workers receive fully resolved payloads only; this module supports planners, tests,
and instance-context enrichment before POST /v1/workflows/instances.
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

    return out


def resolve_placeholder(value: Any, scope: Mapping[str, Any]) -> Any:
    """Resolve ``${var.name}`` placeholders (Python mirror of SQL read-path)."""
    if isinstance(value, dict):
        return {k: resolve_placeholder(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_placeholder(v, scope) for v in value]
    if not isinstance(value, str):
        return value
    m = _PLACEHOLDER_RE.match(value.strip())
    if not m:
        return value
    key = m.group(1)
    if key not in scope:
        raise KeyError(f"unresolved scope variable: {key}")
    return scope[key]


def resolve_input_json_from_template(
    template: Mapping[str, Any], scope: Mapping[str, Any]
) -> Dict[str, Any]:
    """Resolve an action input_template against a flat scope dict (for tests)."""
    return resolve_placeholder(dict(template), scope)


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

    required = ["tool"]
    if entry.step_config_key:
        required.extend(["project", "projectPath"])
    required.extend(entry.context_vars)
    optional = ["outputDir", "centroid1Dir", "centroid2Dir", "taskConfig", "phase", "runId"]
    return ActionInputSpec(
        action_name=action_name,
        required_keys=sorted(set(required)),
        optional_keys=optional,
    )


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
