"""ActionBase: execute fully resolved input_json via CLI subprocess or in-process call."""

from __future__ import annotations

import logging
import subprocess
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

    def build_argv(self, input_json: Dict[str, Any]) -> List[str]:
        cmd = [self.cli_tool]
        project_set = False
        for json_key, flag in self.argv_map.items():
            if json_key in self.project_keys:
                if project_set:
                    continue
                val = self._project_path(input_json)
                cmd.extend([flag, val])
                project_set = True
                continue
            val = input_json.get(json_key)
            if val is not None and str(val) != "":
                cmd.extend([flag, str(val)])
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
    return CliAction(cli_tool=cli, argv_map=argv_map)
