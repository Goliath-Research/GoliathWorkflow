"""Plan sample prep context and start SamplePrepPipeline (direct DB)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ops._paths import REPO_ROOT, ensure_import_paths
from ops.study_lifecycle import resolve_workflow_version_id

_DEFAULT_SAMPLE_PREP_PROGRAM = (
    REPO_ROOT / "workflow_engine" / "domain" / "fixtures" / "sample_prep.program.json"
)


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

    ensure_import_paths()
    from archive_profile_resolver import apply_archive_profile_storage
    from methyl_validation.sample_prep_planner import plan_sample_prep_context
    from resource_profile import DEFAULT_ARCHIVE_PROFILE_KEY, ResourceProfileReader
    from workflow_context import finalize_instance_context

    planner_payload = dict(body)
    planner_payload.setdefault("projectPath", project_path)

    profile_key = str(
        body.get("archiveProfileKey")
        or body.get("archiveStorageKey")
        or body.get("storageKey")
        or DEFAULT_ARCHIVE_PROFILE_KEY
    )
    profile_reader = ResourceProfileReader(db)
    planner_payload = apply_archive_profile_storage(
        planner_payload,
        profile_reader.h5_storage_defaults,
        profile_key=profile_key,
    )

    context = plan_sample_prep_context(planner_payload)
    # Profile / alignment overlays from the start request must survive planning so
    # finalize/seed_pipeline_scope_flags can derive usePangenome / useWgbsPangenome.
    for key in (
        "alignmentMode",
        "pipelineProfile",
        "pipelineProcedure",
        "libraryProtocol",
        "usePangenome",
        "useWgbsPangenome",
        "actionConfig",
        "profilePath",
        "procedurePath",
        "siteConfigPath",
    ):
        if key in body and body[key] is not None:
            context[key] = body[key]
    # Bake site/profile actionConfig, alignment flags, and resolvedConfig__* scope vars.
    context = finalize_instance_context(context)
    if body.get("disableArchive") is True:
        context.pop("sampleStorage", None)
        context.pop("h5Storage", None)
        # Seed JSON null so archive templates resolve var.sampleDestination without
        # Missing scope variable; archive handler skips when destination is null.
        context["sampleDestination"] = None
        context["h5Destination"] = None
        context["disableArchive"] = True

    program_path = body.get("program_path")
    if program_path is None and body.get("workflow_version_id") is None:
        program_path = str(_DEFAULT_SAMPLE_PREP_PROGRAM)

    version_body = dict(body)
    if program_path is not None:
        version_body["program_path"] = program_path

    version_id = resolve_workflow_version_id(
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
