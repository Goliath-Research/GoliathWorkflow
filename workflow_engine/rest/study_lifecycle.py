"""Portal helper: plan validation context, enrich, and start StudyValidationLifecycle."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _ensure_import_paths() -> None:
    for rel in (
        "workflow_engine/domain",
        "workflow_engine/contract",
        "workers",
        "packages/methylvalidation",
    ):
        p = _REPO_ROOT / rel
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _resolve_workflow_version_id(
    dsn: str,
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
    from compiler import compile_domain_program_file

    program = Path(str(program_path)).expanduser().resolve()
    if not program.is_file():
        raise FileNotFoundError(f"program_path not found: {program}")

    project_path = body.get("projectPath")
    result = compile_domain_program_file(program, enrich_context=False)
    spec = result.workflow.model_dump(mode="json")
    if project_path:
        spec.setdefault("context_defaults", {})
    created = create_workflow_definition(dsn, spec)
    return int(created["workflow_version_id"])


def start_study_validation(
    dsn: str,
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
    from workflow_context import enrich_instance_context

    planner_payload = dict(body)
    planner_payload.setdefault("projectPath", project_path)
    planned = plan_validation_context(planner_payload)
    context = enrich_instance_context(planned)

    version_id = _resolve_workflow_version_id(
        dsn,
        body,
        create_workflow_definition=create_workflow_definition,
    )
    instance_id = create_workflow_instance(dsn, version_id, context)
    start_workflow_instance(dsn, instance_id)
    return {
        "instance_id": instance_id,
        "workflow_version_id": version_id,
        "context_json": context,
        "n_iterations": len(context.get("iterations", [])),
    }
