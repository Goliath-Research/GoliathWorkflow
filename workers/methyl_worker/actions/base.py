"""ActionBase: execute validated input via CLI subprocess or in-process call."""

from __future__ import annotations

import inspect
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from ..action_catalog import ActionCatalogEntry
from ..action_execution import (
    ActionExecutionResult,
    ExecutionTimer,
    execution_result_from_output,
    finalize_output,
    validate_input,
)
from ..collectors import (
    ArtifactCollector,
    GenericPipelineCollector,
    ManifestFirstCollector,
    _resolve_dmp_output_dir,
    _resolve_enricher_output_dir,
)
from ..task_models.pipeline_models import (
    CentroidTaskOutput,
    DetectorTaskOutput,
    DmpSelectTaskOutput,
    EnricherTaskOutput,
    GeneFeatureSelectTaskOutput,
    GeneSelectTaskOutput,
    DerivedMeasuresTaskOutput,
    InfoMeasuresTaskOutput,
    MapperTaskOutput,
)
from ..task_models.step_override_models import CentroidBaseConfigOverride, CentroidStepOverride

logger = logging.getLogger(__name__)

InProcessCallable = Callable[..., BaseModel]


def _handler_accepts_runtime(handler: InProcessCallable) -> bool:
    """True when the handler can receive ``runtime`` (4th positional or keyword-only)."""
    try:
        sig = inspect.signature(handler)
    except (TypeError, ValueError):
        return False
    if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()):
        return True
    positional = [
        p
        for p in sig.parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 4:
        return True
    return any(
        p.kind == inspect.Parameter.KEYWORD_ONLY and p.name == "runtime"
        for p in sig.parameters.values()
    )


def _call_in_process_handler(
    handler: InProcessCallable,
    capability: str,
    action_name: str,
    input_model: BaseModel,
    runtime: Any,
) -> BaseModel:
    """Invoke handler with runtime positional or keyword, matching its signature."""
    if not _handler_accepts_runtime(handler):
        return handler(capability, action_name, input_model)

    try:
        sig = inspect.signature(handler)
    except (TypeError, ValueError):
        return handler(capability, action_name, input_model, runtime)

    if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()):
        return handler(capability, action_name, input_model, runtime)

    positional = [
        p
        for p in sig.parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 4:
        return handler(capability, action_name, input_model, runtime)

    return handler(capability, action_name, input_model, runtime=runtime)


DEFAULT_PIPELINE_ARGV_MAP: Dict[str, str] = {
    "project": "--project",
    "projectPath": "--project",
    "project_path": "--project",
    "group": "--group",
    "chromosome": "--chromosome",
    "context": "--context",
    "comparison": "--comparison",
    "outputDir": "--output-dir",
    "centroid1Dir": "--centroid1-dir",
    "centroid2Dir": "--centroid2-dir",
    "stepOverride": "--step-override",
    "fixedDmpPanel": "--fixed-dmp-panel",
}


@runtime_checkable
class ActionBase(Protocol):
    execution_mode: str
    entry: ActionCatalogEntry

    def execute(self, input_json: Mapping[str, Any]) -> ActionExecutionResult: ...


class CliAction:
    """Run a console script built from catalog argv_map + resolved input_json."""

    execution_mode = "cli"

    def __init__(
        self,
        *,
        entry: ActionCatalogEntry,
        cli_tool: str,
        argv_map: Mapping[str, str],
        collector: Optional[ArtifactCollector] = None,
        project_keys: tuple[str, ...] = ("project", "projectPath", "project_path"),
    ) -> None:
        self.entry = entry
        self.cli_tool = cli_tool
        self.argv_map = dict(argv_map)
        self.collector = collector or GenericPipelineCollector()
        self.project_keys = project_keys

    def _project_path(self, input_json: Mapping[str, Any]) -> str:
        for key in self.project_keys:
            val = input_json.get(key)
            if val:
                return str(val)
        task_cfg = input_json.get("taskConfig")
        if isinstance(task_cfg, dict):
            for key in self.project_keys + ("projectJson",):
                val = task_cfg.get(key)
                if val:
                    return str(val)
        raise RuntimeError("input_json missing project / projectPath")

    def _materialize_resolved_config_path(self, input_json: Mapping[str, Any]) -> Optional[str]:
        """Write task resolvedConfig slice to a temp JSON file for --resolved-config."""
        resolved = input_json.get("resolvedConfig")
        if not isinstance(resolved, dict) or not resolved:
            return None
        fd, path = tempfile.mkstemp(suffix=".json", prefix="resolved-config-")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(resolved, f)
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise
        return path

    def _argv_value(self, json_key: str, val: Any) -> Optional[str]:
        if val is None or val == "":
            return None
        if json_key == "stepOverride" and isinstance(val, dict):
            fd, path = tempfile.mkstemp(suffix=".json", prefix="step-override-")
            try:
                with open(fd, "w", encoding="utf-8") as f:
                    json.dump(val, f)
            except Exception:
                Path(path).unlink(missing_ok=True)
                raise
            return path
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val)

    def build_argv(self, input_json: Mapping[str, Any]) -> List[str]:
        data = dict(input_json)
        resolved_path = self._materialize_resolved_config_path(data)
        if resolved_path is not None:
            data["resolvedConfigPath"] = resolved_path
        cmd = [self.cli_tool]
        project_set = False
        step_override: Optional[Dict[str, Any]] = data.get("stepOverride")  # type: ignore[assignment]
        if step_override is None:
            add_samples = data.get("addSamples")
            remove_samples = data.get("removeSamples")
            if add_samples is not None or remove_samples is not None:
                step_override = CentroidStepOverride(
                    base_config=CentroidBaseConfigOverride(
                        add_samples=list(add_samples or []),
                        remove_samples=list(remove_samples or []),
                    )
                ).model_dump(mode="json", exclude_none=True)
        if step_override is not None and data.get("stepOverride") is None:
            data = {**data, "stepOverride": step_override}
        for json_key, flag in self.argv_map.items():
            if json_key in self.project_keys:
                if project_set:
                    continue
                val = self._project_path(data)
                cmd.extend([flag, val])
                project_set = True
                continue
            val = data.get(json_key)
            argv_val = self._argv_value(json_key, val)
            if argv_val is not None:
                cmd.extend([flag, argv_val])
        if not project_set and any(k in self.argv_map for k in self.project_keys):
            cmd.extend([self.argv_map[self.project_keys[0]], self._project_path(data)])
        return cmd

    @staticmethod
    def _format_subprocess_failure(cmd: List[str], proc: subprocess.CompletedProcess[str]) -> str:
        parts = [f"{cmd[0]} exited {proc.returncode}"]
        for label, text in (("stderr", proc.stderr), ("stdout", proc.stdout)):
            tail = (text or "").strip()
            if not tail:
                continue
            lines = tail.splitlines()
            if len(lines) > 40:
                tail = "\n".join(lines[-40:])
                parts.append(f"{label} (last 40 lines):\n{tail}")
            else:
                parts.append(f"{label}:\n{tail}")
        if len(parts) == 1:
            parts.append("no stderr/stdout captured")
        return "\n".join(parts)

    def execute(self, input_json: Mapping[str, Any]) -> ActionExecutionResult:
        from ..task_validation import extract_runtime_input, strip_runtime_input

        payload = dict(input_json)
        runtime = extract_runtime_input(payload)
        task_payload = strip_runtime_input(payload)
        input_model = validate_input(self.entry, task_payload)
        argv_payload = {**input_model.model_dump(mode="json"), **runtime}
        timer = ExecutionTimer()
        cmd = self.build_argv(argv_payload)
        logger.info("Running: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        try:
            from methyl_utils.gpu_detection import cleanup_gpu_memory

            cleanup_gpu_memory()
        except Exception:
            pass
        finished_at, duration_ms = timer.finish()
        if proc.returncode != 0:
            raise RuntimeError(self._format_subprocess_failure(cmd, proc))
        collected = self.collector.collect(
            argv_payload,
            action_name=self.entry.action_name,
            stdout=proc.stdout or "",
        )
        collected.setdefault("tool", self.cli_tool)
        collected.setdefault("stdout_tail", (proc.stdout or "")[-500:])
        manifest_path = collected.get("manifest_path")
        output = finalize_output(
            self.entry,
            collected,
            started_at=timer.started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            exit_code=proc.returncode,
            manifest_path=str(manifest_path) if manifest_path else None,
        )
        return execution_result_from_output(output)


class InProcessAction:
    """Invoke a Python handler with validated input; returns typed output."""

    execution_mode = "in_process"

    def __init__(
        self,
        handler: InProcessCallable,
        *,
        entry: ActionCatalogEntry,
    ) -> None:
        self.handler = handler
        self.entry = entry

    def execute(self, input_json: Mapping[str, Any]) -> ActionExecutionResult:
        from ..task_validation import parse_task_envelope

        input_model, runtime = parse_task_envelope(
            self.entry.action_name,
            self.entry.capability,
            input_json,
        )
        timer = ExecutionTimer()
        raw = _call_in_process_handler(
            self.handler,
            self.entry.capability,
            self.entry.action_name,
            input_model,
            runtime,
        )
        finished_at, duration_ms = timer.finish()
        if not isinstance(raw, BaseModel):
            raise TypeError(
                f"In-process handler for {self.entry.action_name!r} must return BaseModel, got {type(raw)!r}"
            )
        output = finalize_output(
            self.entry,
            raw.model_dump(mode="json"),
            started_at=timer.started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            exit_code=0,
            manifest_path=getattr(raw, "manifest_path", None),
        )
        return execution_result_from_output(output)


def _collector_for_entry(entry: ActionCatalogEntry) -> ArtifactCollector:
    name = entry.action_name
    if name == "pipeline.dmp_select":
        return ManifestFirstCollector(
            output_model=DmpSelectTaskOutput,
            resolve_output_dir=lambda inp: _resolve_dmp_output_dir(inp),
        )
    if name == "pipeline.gene_select":
        return ManifestFirstCollector(
            output_model=GeneSelectTaskOutput,
            resolve_output_dir=lambda inp: inp.get("runDir"),
        )
    if name == "pipeline.gene_feature_select":
        return ManifestFirstCollector(
            output_model=GeneFeatureSelectTaskOutput,
            resolve_output_dir=lambda inp: inp.get("outputDir"),
        )
    if name == "pipeline.detector":
        return ManifestFirstCollector(
            output_model=DetectorTaskOutput,
            resolve_output_dir=lambda inp: inp.get("outputDir"),
        )
    if name == "pipeline.mapper":
        return ManifestFirstCollector(
            output_model=MapperTaskOutput,
            resolve_output_dir=lambda inp: inp.get("outputDir"),
        )
    if name == "pipeline.derived_measures":
        return ManifestFirstCollector(
            output_model=DerivedMeasuresTaskOutput,
            resolve_output_dir=lambda inp: inp.get("outputDir"),
        )
    if name == "pipeline.info_measures":
        return ManifestFirstCollector(
            output_model=InfoMeasuresTaskOutput,
            resolve_output_dir=lambda inp: inp.get("outputDir"),
        )
    if name == "pipeline.centroid":
        return ManifestFirstCollector(
            output_model=CentroidTaskOutput,
            resolve_output_dir=lambda inp: inp.get("outputDir"),
        )
    if name == "pipeline.enricher":
        return ManifestFirstCollector(
            output_model=EnricherTaskOutput,
            resolve_output_dir=_resolve_enricher_output_dir,
        )
    return GenericPipelineCollector()


def build_action_from_catalog(entry: ActionCatalogEntry, handlers_module: Any) -> ActionBase:
    if entry.execution_mode == "in_process":
        handler_name = entry.in_process_handler or entry.handler
        handler = getattr(handlers_module, handler_name, None)
        if handler is None or not callable(handler):
            raise RuntimeError(f"Missing in-process handler {handler_name!r} for {entry.action_name}")
        return InProcessAction(handler, entry=entry)

    cli = entry.cli_tool
    if cli is None:
        raise RuntimeError(f"Action {entry.action_name!r} has execution_mode=cli but no cli_tool")

    argv_map = dict(entry.argv_map) if entry.argv_map else dict(DEFAULT_PIPELINE_ARGV_MAP)
    collector = _collector_for_entry(entry)
    if entry.action_name == "pipeline.detector":
        from .detector import DETECTOR_ARGV_MAP, DetectorCliAction

        return DetectorCliAction(entry=entry, cli_tool=cli, argv_map=DETECTOR_ARGV_MAP, collector=collector)
    if entry.action_name == "pipeline.dmp_select":
        from .dmp_select import DMP_SELECT_ARGV_MAP, DmpSelectCliAction

        return DmpSelectCliAction(entry=entry, cli_tool=cli, argv_map=DMP_SELECT_ARGV_MAP, collector=collector)
    if entry.action_name == "pipeline.mapper":
        from .mapper import MAPPER_ARGV_MAP, MapperCliAction

        return MapperCliAction(entry=entry, cli_tool=cli, argv_map=MAPPER_ARGV_MAP, collector=collector)
    if entry.action_name == "pipeline.derived_measures":
        from .derived_measures import DERIVED_MEASURES_ARGV_MAP, DerivedMeasuresCliAction

        return DerivedMeasuresCliAction(
            entry=entry, cli_tool=cli, argv_map=DERIVED_MEASURES_ARGV_MAP, collector=collector
        )
    if entry.action_name == "pipeline.info_measures":
        from .info_measures import INFO_MEASURES_ARGV_MAP, InfoMeasuresCliAction

        return InfoMeasuresCliAction(
            entry=entry, cli_tool=cli, argv_map=INFO_MEASURES_ARGV_MAP, collector=collector
        )
    if entry.action_name == "pipeline.gene_select":
        from .gene_select import GENE_SELECT_ARGV_MAP, GeneSelectCliAction

        return GeneSelectCliAction(entry=entry, cli_tool=cli, argv_map=GENE_SELECT_ARGV_MAP, collector=collector)
    if entry.action_name == "pipeline.gene_feature_select":
        from .gene_feature_select import GENE_FEATURE_SELECT_ARGV_MAP, GeneFeatureSelectCliAction

        return GeneFeatureSelectCliAction(
            entry=entry, cli_tool=cli, argv_map=GENE_FEATURE_SELECT_ARGV_MAP, collector=collector
        )
    if entry.action_name == "pipeline.centroid":
        from .centroid import CentroidCliAction

        return CentroidCliAction(entry=entry, cli_tool=cli, argv_map=argv_map, collector=collector)
    if entry.action_name == "pipeline.enricher":
        from .enricher import ENRICHER_ARGV_MAP, EnricherCliAction

        return EnricherCliAction(entry=entry, cli_tool=cli, argv_map=ENRICHER_ARGV_MAP, collector=collector)
    return CliAction(entry=entry, cli_tool=cli, argv_map=argv_map, collector=collector)
