"""pipeline.centroid CLI action with optional shared seed baseline copy."""

from __future__ import annotations

import logging
import subprocess
from typing import Any, Mapping

from ..action_execution import ActionExecutionResult, execution_result_from_output, validate_input
from .base import CliAction, ExecutionTimer, finalize_output

logger = logging.getLogger(__name__)


class CentroidCliAction(CliAction):
    """Copy ``centroidSeedDir`` into ``outputDir`` before incremental methyl-centroid runs."""

    def execute(self, input_json: Mapping[str, Any]) -> ActionExecutionResult:
        from ..task_validation import extract_runtime_input, strip_runtime_input

        payload = dict(input_json)
        runtime = extract_runtime_input(payload)
        task_payload = strip_runtime_input(payload)
        input_model = validate_input(self.entry, task_payload)
        argv_payload = {**input_model.model_dump(mode="json"), **runtime}

        seed_dir = argv_payload.get("centroidSeedDir")
        output_dir = argv_payload.get("outputDir")
        if seed_dir and output_dir:
            from methyl_validation.project_gen import copy_centroid_seed_baseline

            copy_centroid_seed_baseline(seed_dir, output_dir)

        timer = ExecutionTimer()
        cmd = self.build_argv(argv_payload)
        logger.info("Running: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
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
            manifest_path=manifest_path,
        )
        return execution_result_from_output(output)
