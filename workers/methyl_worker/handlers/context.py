"""Context / planner in-process handlers."""

from __future__ import annotations

import logging
from typing import Any, Dict

from pydantic import BaseModel

from ..task_models.runtime_models import TaskRuntimeContext

logger = logging.getLogger(__name__)

def _handle_context_resolve_project(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    runtime: TaskRuntimeContext,
):
    from methyl_domain.helpers import build_resolved_project
    from methyl_domain.types import to_tagged_json

    from ..task_models.context_models import ResolveProjectTaskInput, ResolveProjectTaskOutput

    req = (
        input
        if isinstance(input, ResolveProjectTaskInput)
        else ResolveProjectTaskInput.model_validate(input.model_dump(mode="json"))
    )
    del runtime
    cohort_paths = None
    if req.cohortPathsList:
        cohort_paths = [(label, list(paths)) for label, paths in req.cohortPathsList]
    resolved = build_resolved_project(
        req.projectPath,
        monte_carlo_runs_root=req.monteCarloRunsRoot,
        cohort_paths_list=cohort_paths,
    )
    tagged = to_tagged_json(resolved)
    return ResolveProjectTaskOutput(status="ok", resolvedProject=tagged)


def _handle_validation_plan_iterations(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    runtime: TaskRuntimeContext,
):
    from methyl_validation.workflow_planner import ValidationPlanRequest, plan_validation_context

    from ..task_models.validation_models import ValidationPlanTaskOutput

    request = (
        input
        if isinstance(input, ValidationPlanRequest)
        else ValidationPlanRequest.model_validate(input.model_dump(mode="json"))
    )
    if not isinstance(runtime, TaskRuntimeContext):
        runtime = TaskRuntimeContext.from_wire({})

    context = plan_validation_context(request, profile_overrides=runtime.validationProfile)
    return ValidationPlanTaskOutput(
        status="ok",
        projectPath=context.projectPath,
        n_iterations=len(context.iterations),
        centroidSeedGroups=context.centroidSeedGroups,
        iterations=context.iterations,
    )



