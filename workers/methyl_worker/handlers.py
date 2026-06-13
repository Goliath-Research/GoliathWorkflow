"""Dispatch workflow ACTION tasks to local methyl-* CLIs and sample-prep handlers."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

HandlerResult = Dict[str, Any]
Handler = Callable[[str, str, Dict[str, Any]], HandlerResult]

from .action_catalog import build_capability_handlers, build_tool_cli_map

# input_json "tool" field -> console script name
TOOL_CLI: Dict[str, str] = build_tool_cli_map()

# wf.workflow_action.capability -> handler function name
CAPABILITY_HANDLERS: Dict[str, str] = build_capability_handlers()


def _project_path(input_json: Dict[str, Any]) -> Optional[str]:
    for key in ("project", "projectPath", "project_path"):
        val = input_json.get(key)
        if val:
            return str(val)
    return None


def _run_subprocess(cmd: list[str]) -> str:
    logger.info("Running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"{cmd[0]} failed")
    return (proc.stdout or "")[-500:]


def _handle_pipeline_cli(_capability: str, action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    tool = str(input_json.get("tool") or action_name)
    cli = TOOL_CLI.get(tool)
    if cli is None and tool.startswith("pipeline."):
        cli = TOOL_CLI.get(tool.split(".", 1)[-1])
    if cli is None:
        raise RuntimeError(f"Unknown tool {tool!r} for capability {capability!r}")

    project = _project_path(input_json)
    task_cfg = input_json.get("taskConfig")
    if not project and isinstance(task_cfg, dict):
        for key in ("projectJson", "projectPath", "project"):
            val = task_cfg.get(key)
            if val:
                project = str(val)
                break
    if not project:
        raise RuntimeError("input_json missing project / projectPath")

    cmd = [cli, "--project", project]

    flag_map = {
        "group": "--group",
        "chromosome": "--chromosome",
        "context": "--context",
        "comparison": "--comparison",
        "outputDir": "--output-dir",
        "centroid1Dir": "--centroid1-dir",
        "centroid2Dir": "--centroid2-dir",
    }
    for json_key, flag in flag_map.items():
        val = input_json.get(json_key)
        if val is not None and str(val) != "":
            cmd.extend([flag, str(val)])

    stdout_tail = _run_subprocess(cmd)
    return {"status": "ok", "tool": cli, "stdout_tail": stdout_tail}


def _handle_methyl_qc(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir:
        raise RuntimeError("methyl-qc task requires sampleDir in input_json")

    sample_path = Path(str(sample_dir))
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")

    project = _project_path(input_json)
    from methyl_alignment_qc.core import process_samples_to_qc_jsons

    if project:
        from methyl_alignment_qc.project_resolver import resolve_alignment_qc_config

        cfg = resolve_alignment_qc_config(project)
        out_dir = cfg.output_dir
        process_samples_to_qc_jsons(
            [str(sample_path)],
            out_dir,
            validate_schema=cfg.validate_schema,
            fragmentomics=cfg.fragmentomics,
            bisulfite_conversion=cfg.bisulfite_conversion,
        )
        qc_path = Path(out_dir) / f"{sample_path.name}.json"
    else:
        with tempfile.TemporaryDirectory(prefix="methyl-qc-") as tmp:
            out_dir = tmp
            process_samples_to_qc_jsons([str(sample_path)], out_dir)
            qc_path = Path(out_dir) / f"{sample_path.name}.json"
            payload = json.loads(qc_path.read_text(encoding="utf-8"))
            guardrails = payload.get("guardrails") or {}
            return {
                "sampleId": sample_id or sample_path.name,
                "qcPath": str(qc_path),
                "guardrails": guardrails,
            }

    if not qc_path.is_file():
        raise RuntimeError(f"QC JSON not written: {qc_path}")

    payload = json.loads(qc_path.read_text(encoding="utf-8"))
    guardrails = payload.get("guardrails") or {}
    return {
        "sampleId": sample_id or sample_path.name,
        "qcPath": str(qc_path),
        "guardrails": guardrails,
    }


def _handle_methyl_fragmentomics(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    project = _project_path(input_json)
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not project:
        raise RuntimeError("methyl-fragmentomics task requires project in input_json")
    if not sample_dir:
        raise RuntimeError("methyl-fragmentomics task requires sampleDir in input_json")

    sample_path = Path(str(sample_dir))
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")

    from methyl_fragmentomics.project_resolver import resolve_fragmentomics_step_config
    from methyl_fragmentomics.core.runner import run_fragmentomics_for_samples
    from methyl_utils import load_project

    cfg, _sample_dirs, out_dir = resolve_fragmentomics_step_config(project)
    project_obj = load_project(project)
    summary = run_fragmentomics_for_samples(
        [str(sample_path)],
        Path(out_dir),
        cfg,
        project_chromosomes=project_obj.chromosomes,
    )

    sid = sample_id or sample_path.name
    return {
        "sampleId": sid,
        "outputDir": str(Path(out_dir) / sid),
        "summary": summary.get("samples", {}).get(sid, {}),
    }


def _handle_validation_plan_iterations(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    """Monte Carlo planner: materialize run projects and return ValidationPipeline context_json."""
    from methyl_validation.workflow_planner import plan_validation_context

    context = plan_validation_context(input_json)
    return {
        "status": "ok",
        "context_json": context,
        "iterations": context.get("iterations", []),
        "n_iterations": len(context.get("iterations", [])),
        "projectPath": context.get("projectPath"),
    }


def _handle_mark_failed(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    return {
        "sampleId": input_json.get("sampleId"),
        "sampleDir": input_json.get("sampleDir"),
        "status": "QC_FAILED",
        "reason": input_json.get("reason", "alignment_qc_failed"),
    }


def _handle_stub_external(capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    if os.environ.get("WORKER_STUB_EXTERNAL", "").lower() in {"1", "true", "yes"}:
        logger.warning("WORKER_STUB_EXTERNAL: faking success for %s", capability)
        sample_id = input_json.get("sampleId", "unknown")
        sample_dir = input_json.get("sampleDir", "")
        if capability == "sample.download-fastq":
            return {"sampleId": sample_id, "fastqFiles": ["R1.fastq.gz", "R2.fastq.gz"]}
        if capability == "parabricks.fq2bam":
            bam = f"{sample_dir}/{sample_id}.bam" if sample_dir else f"{sample_id}.bam"
            return {
                "sampleId": sample_id,
                "bamPath": bam,
                "metricsJson": f"{sample_dir}/{sample_id}.json" if sample_dir else f"{sample_id}.json",
            }
        if capability == "sample.delete-fastqs":
            return {"sampleId": sample_id, "deleted": True}
        if capability == "sample.delete-bam":
            return {"sampleId": sample_id, "deleted": True}
        if capability == "methyl-extract":
            return {"sampleId": sample_id, "h5Files": ["1-CG.h5"]}
    raise RuntimeError(
        f"No local handler for capability {capability!r}. "
        "Implement a domain worker or set WORKER_STUB_EXTERNAL=1 for dry-run."
    )


def execute_task(capability: str, action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    """Run one ACTION and return output_json for sp_worker_submit_result."""
    handler_key = CAPABILITY_HANDLERS.get(capability)
    if handler_key is None:
        return _handle_pipeline_cli(capability, action_name, input_json)

    dispatch: Dict[str, Handler] = {
        "_handle_pipeline_cli": _handle_pipeline_cli,
        "_handle_methyl_qc": _handle_methyl_qc,
        "_handle_methyl_fragmentomics": _handle_methyl_fragmentomics,
        "_handle_mark_failed": _handle_mark_failed,
        "_handle_validation_plan_iterations": _handle_validation_plan_iterations,
        "_handle_stub_external": _handle_stub_external,
    }
    handler = dispatch[handler_key]
    return handler(capability, action_name, input_json)
