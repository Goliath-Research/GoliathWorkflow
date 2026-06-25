"""LocalWorkflowEngine — run WorkflowDefinitionSpec in-process."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel

_DOMAIN = Path(__file__).resolve().parents[1] / "domain"
_CONTRACT = Path(__file__).resolve().parents[1] / "contract"
if str(_DOMAIN) not in sys.path:
    sys.path.insert(0, str(_DOMAIN))
if str(_CONTRACT) not in sys.path:
    sys.path.insert(0, str(_CONTRACT))

from compiler import compile_domain_program, compile_domain_program_file  # noqa: E402
from workflow_definition_spec import WorkflowDefinitionSpec  # noqa: E402
from workflow_context import enrich_instance_context  # noqa: E402

from .scheduler import ExecutionTrace, SchedulerConfig, WorkflowScheduler
from .scope import ScopeFrame, resolve_collection_bindings

logger = logging.getLogger(__name__)

ActionHandler = Callable[[str, str, Dict[str, Any]], BaseModel]


@dataclass
class RunResult:
    status: str
    trace: ExecutionTrace
    scope: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class LocalWorkflowEngine:
    """Execute a workflow definition locally without gateway or database."""

    def __init__(
        self,
        *,
        handler: Optional[ActionHandler] = None,
        config: Optional[SchedulerConfig] = None,
    ) -> None:
        self.config = config or SchedulerConfig()
        self._handler = handler

    def _default_handler(self) -> ActionHandler:
        _workers = Path(__file__).resolve().parents[2] / "workers"
        if str(_workers) not in sys.path:
            sys.path.insert(0, str(_workers))
        from methyl_worker.handlers import execute_task
        from methyl_worker.task_validation import (
            TaskValidationError,
            validate_task_input,
            validate_task_output,
        )

        def _run(capability: str, action_name: str, input_json: Dict[str, Any]) -> BaseModel:
            from methyl_worker.task_validation import normalize_task_input

            input_json = normalize_task_input(action_name, capability, input_json)
            validate_task_input(action_name, capability, input_json)
            execution = execute_task(capability, action_name, input_json)
            return validate_task_output(action_name, capability, execution.output)

        return _run

    def run_spec(
        self,
        spec: WorkflowDefinitionSpec,
        context_json: Dict[str, Any],
        *,
        enrich_context: bool = True,
    ) -> RunResult:
        context = dict(context_json)
        if enrich_context:
            try:
                context = enrich_instance_context(context)
            except (FileNotFoundError, ValueError) as exc:
                logger.warning("context enrichment skipped: %s", exc)

        scope_data = resolve_collection_bindings(spec.collection_bindings, context)
        scope = ScopeFrame(scope_data)
        handler = self._handler or self._default_handler()
        os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

        try:
            scheduler = WorkflowScheduler(
                spec, scope, handler=handler, config=self.config
            )
            trace = scheduler.run()
            return RunResult(status="COMPLETED", trace=trace, scope=scope.as_flat_dict())
        except Exception as exc:
            logger.exception("workflow run failed")
            return RunResult(
                status="FAILED",
                trace=ExecutionTrace(),
                scope=scope.as_flat_dict(),
                error=str(exc),
            )

    def run_program(
        self,
        program_path: Path,
        context_json: Dict[str, Any],
        *,
        enrich_context: bool = True,
    ) -> RunResult:
        result = compile_domain_program_file(program_path, enrich_context=False)
        merged = {**result.context_json, **context_json}
        return self.run_spec(result.workflow, merged, enrich_context=enrich_context)

    @staticmethod
    def load_spec(path: Path) -> WorkflowDefinitionSpec:
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkflowDefinitionSpec.model_validate(data)
