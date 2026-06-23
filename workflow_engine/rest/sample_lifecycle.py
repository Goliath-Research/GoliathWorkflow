"""Portal helper: plan sample prep context and start SamplePrepPipeline."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_SAMPLE_PREP_PROGRAM = (
    _REPO_ROOT / "workflow_engine" / "domain" / "fixtures" / "sample_prep.program.json"
)


def _ensure_import_paths() -> None:
    for rel in (
        "workflow_engine/domain",
        "workflow_engine/contract",
        "workers",
        "packages/methyldomain",
        "packages/methylvalidation",
    ):
        p = _REPO_ROOT / rel
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def start_sample_prep(
    db: Any,
    body: Dict[str, Any],
    *,
    create_workflow_definition,
    create_workflow_instance,
    start_workflow_instance,
) -> Dict[str, Any]:
    """Plan samples, build context_json, create and start SamplePrepPipeline."""
    project_path = body.get("projectPath")
    if not project_path:
        raise ValueError("projectPath is required")

    _ensure_import_paths()
    from methyl_validation.sample_prep_planner import plan_sample_prep_context
    from study_lifecycle import _resolve_workflow_version_id

    planner_payload = dict(body)
    planner_payload.setdefault("projectPath", project_path)

    from methyl_domain.platform_storage import DEFAULT_STORAGE_KEY
    try:
        from .platform_storage import apply_platform_sample_storage
    except ImportError:
        from platform_storage import apply_platform_sample_storage

    storage_key = str(body.get("storageKey") or DEFAULT_STORAGE_KEY)
    platform_row = db.get_platform_sample_storage(storage_key)
    planner_payload = apply_platform_sample_storage(
        planner_payload,
        platform_row,
        storage_key=storage_key,
    )

    context = plan_sample_prep_context(planner_payload)

    program_path = body.get("program_path")
    if program_path is None and body.get("workflow_version_id") is None:
        program_path = str(_DEFAULT_SAMPLE_PREP_PROGRAM)

    version_body = dict(body)
    if program_path is not None:
        version_body["program_path"] = program_path

    version_id = _resolve_workflow_version_id(
        db,
        version_body,
        create_workflow_definition=create_workflow_definition,
    )
    instance_id = create_workflow_instance(db, version_id, context)
    start_workflow_instance(db, instance_id)
    return {
        "instance_id": instance_id,
        "workflow_version_id": version_id,
        "context_json": context,
        "n_samples": len(context.get("samples") or []),
    }
