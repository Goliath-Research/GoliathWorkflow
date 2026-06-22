"""ActionBase: execute fully resolved input_json via CLI subprocess or in-process call."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

HandlerResult = Dict[str, Any]
InProcessCallable = Callable[[str, str, Dict[str, Any]], HandlerResult]

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

    def execute(self, input_json: Dict[str, Any]) -> HandlerResult: ...


class CliAction:
    """Run a console script built from catalog argv_map + resolved input_json."""

    execution_mode = "cli"

    def __init__(
        self,
        *,
        cli_tool: str,
        argv_map: Mapping[str, str],
        project_keys: tuple[str, ...] = ("project", "projectPath", "project_path"),
    ) -> None:
        self.cli_tool = cli_tool
        self.argv_map = dict(argv_map)
        self.project_keys = project_keys

    def _project_path(self, input_json: Dict[str, Any]) -> str:
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

    def _argv_value(self, json_key: str, val: Any) -> Optional[str]:
        if val is None or val == "":
            return None
        if json_key == "stepOverride" and isinstance(val, dict):
            add_samples = val.get("base_config", {}).get("add_samples")
            remove_samples = val.get("base_config", {}).get("remove_samples")
            if add_samples is None and remove_samples is None:
                payload = val
            else:
                payload = val
            fd, path = tempfile.mkstemp(suffix=".json", prefix="step-override-")
            try:
                with open(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f)
            except Exception:
                Path(path).unlink(missing_ok=True)
                raise
            return path
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val)

    def build_argv(self, input_json: Dict[str, Any]) -> List[str]:
        cmd = [self.cli_tool]
        project_set = False
        step_override: Optional[Dict[str, Any]] = input_json.get("stepOverride")
        if step_override is None:
            add_samples = input_json.get("addSamples")
            remove_samples = input_json.get("removeSamples")
            if add_samples is not None or remove_samples is not None:
                step_override = {
                    "base_config": {
                        "add_samples": list(add_samples or []),
                        "remove_samples": list(remove_samples or []),
                    }
                }
        if step_override is not None and input_json.get("stepOverride") is None:
            input_json = {**input_json, "stepOverride": step_override}
        for json_key, flag in self.argv_map.items():
            if json_key in self.project_keys:
                if project_set:
                    continue
                val = self._project_path(input_json)
                cmd.extend([flag, val])
                project_set = True
                continue
            val = input_json.get(json_key)
            argv_val = self._argv_value(json_key, val)
            if argv_val is not None:
                cmd.extend([flag, argv_val])
        if not project_set and any(k in self.argv_map for k in self.project_keys):
            cmd.extend([self.argv_map[self.project_keys[0]], self._project_path(input_json)])
        return cmd

    def execute(self, input_json: Dict[str, Any]) -> HandlerResult:
        cmd = self.build_argv(input_json)
        logger.info("Running: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"{cmd[0]} failed")
        return {
            "status": "ok",
            "tool": self.cli_tool,
            "stdout_tail": (proc.stdout or "")[-500:],
        }


class InProcessAction:
    """Invoke a Python handler with (capability, action_name, input_json)."""

    execution_mode = "in_process"

    def __init__(
        self,
        handler: InProcessCallable,
        *,
        capability: str,
        action_name: str,
    ) -> None:
        self.handler = handler
        self.capability = capability
        self.action_name = action_name

    def execute(self, input_json: Dict[str, Any]) -> HandlerResult:
        return self.handler(self.capability, self.action_name, input_json)


def build_action_from_catalog(entry, handlers_module: Any) -> ActionBase:
    if entry.execution_mode == "in_process":
        handler_name = entry.in_process_handler or entry.handler
        handler = getattr(handlers_module, handler_name, None)
        if handler is None or not callable(handler):
            raise RuntimeError(f"Missing in-process handler {handler_name!r} for {entry.action_name}")
        return InProcessAction(
            handler,
            capability=entry.capability,
            action_name=entry.action_name,
        )

    cli = entry.cli_tool
    if cli is None:
        raise RuntimeError(f"Action {entry.action_name!r} has execution_mode=cli but no cli_tool")

    argv_map = dict(entry.argv_map) if entry.argv_map else dict(DEFAULT_PIPELINE_ARGV_MAP)
    if entry.action_name == "pipeline.detector":
        from .detector import DETECTOR_ARGV_MAP, DetectorCliAction

        return DetectorCliAction(cli_tool=cli, argv_map=DETECTOR_ARGV_MAP)
    if entry.action_name == "pipeline.dmp_select":
        from .dmp_select import DMP_SELECT_ARGV_MAP, DmpSelectCliAction

        return DmpSelectCliAction(cli_tool=cli, argv_map=DMP_SELECT_ARGV_MAP)
    if entry.action_name == "pipeline.gene_select":
        from .gene_select import GENE_SELECT_ARGV_MAP, GeneSelectCliAction

        return GeneSelectCliAction(cli_tool=cli, argv_map=GENE_SELECT_ARGV_MAP)
    return CliAction(cli_tool=cli, argv_map=argv_map)
