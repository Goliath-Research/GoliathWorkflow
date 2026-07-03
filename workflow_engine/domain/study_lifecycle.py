"""Admin tooling: plan validation context, enrich, and start StudyValidationLifecycle."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _ensure_import_paths() -> None:
    domain = _REPO_ROOT / "workflow_engine" / "domain"
    if str(domain) not in sys.path:
        sys.path.insert(0, str(domain))
    for rel in (
        "workflow_engine/contract",
        "workers",
        "packages/methyldomain",
        "packages/methylvalidation",
    ):
        p = _REPO_ROOT / rel
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _apply_project_path_scope_default(spec: Dict[str, Any], project_path: str) -> None:
    """Pin projectPath on the workflow definition for instances started without full context."""
    resolved = str(Path(str(project_path)).expanduser().resolve())
    root_key = str(spec.get("root_node_key") or "root")
    scope_defaults: list[Dict[str, Any]] = list(spec.get("scope_defaults") or [])
    for item in scope_defaults:
        if item.get("var_name") == "projectPath":
            item["default_expr"] = json.dumps(resolved)
            break
    else:
        scope_defaults.append(
            {
                "node_key": root_key,
                "var_name": "projectPath",
                "default_expr": json.dumps(resolved),
            }
        )
    spec["scope_defaults"] = scope_defaults


def compile_program_spec(program: Path, *, project_path: Optional[str] = None) -> Dict[str, Any]:
    from compiler import compile_domain_program
    from methyl_domain.program import DomainProgram

    program_model = DomainProgram.model_validate(
        json.loads(program.read_text(encoding="utf-8"))
    )
    effective_path = project_path or program_model.projectPath
    if effective_path:
        program_model = program_model.model_copy(
            update={"projectPath": str(Path(str(effective_path)).expanduser().resolve())}
        )
    result = compile_domain_program(program_model, enrich_context=False)
    spec = result.workflow.model_dump(mode="json")
    if effective_path:
        _apply_project_path_scope_default(spec, effective_path)
    return spec


def resolve_workflow_version_id(
    db: Any,
    body: Dict[str, Any],
    *,
    create_workflow_definition,
) -> int:
    raw = body.get("workflow_version_id")
    if raw is not None:
        return int(raw)

    program_path = body.get("program_path")
    if not program_path:
        raise ValueError("workflow_version_id or program_path is required")

    _ensure_import_paths()

    program = Path(str(program_path)).expanduser().resolve()
    if not program.is_file():
        raise FileNotFoundError(f"program_path not found: {program}")

    project_path = body.get("projectPath")
    spec = compile_program_spec(program, project_path=project_path)
    created = create_workflow_definition(db, spec)
    return int(created["workflow_version_id"])


def start_study_validation(
    db: Any,
    body: Dict[str, Any],
    *,
    create_workflow_definition,
    create_workflow_instance,
    start_workflow_instance,
) -> Dict[str, Any]:
    """Plan iterations, enrich instance context, create and start a validation workflow."""
    project_path = body.get("projectPath")
    if not project_path:
        raise ValueError("projectPath is required")

    _ensure_import_paths()
    from methyl_validation.workflow_planner import plan_validation_context
    from workflow_context import finalize_instance_context

    planner_payload = dict(body)
    planner_payload.setdefault("projectPath", project_path)
    planned = plan_validation_context(planner_payload)
    context = finalize_instance_context(planned.model_dump(mode="json"))

    version_id = resolve_workflow_version_id(
        db,
        body,
        create_workflow_definition=create_workflow_definition,
    )
    instance_id = create_workflow_instance(db, version_id, context)
    start_workflow_instance(db, instance_id)
    return {
        "instance_id": instance_id,
        "workflow_version_id": version_id,
        "context_json": context,
        "n_iterations": len(context.get("iterations", [])),
    }
