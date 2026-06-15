"""Dispatch workflow ACTION tasks to catalog-defined CLI or in-process executors."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

HandlerResult = Dict[str, Any]
Handler = Callable[[str, str, Dict[str, Any]], HandlerResult]

from .action_catalog import (
    ACTION_CATALOG,
    build_capability_handlers,
    build_tool_cli_map,
    find_catalog_entry,
    find_catalog_entry_by_capability,
)
from .actions.base import build_action_from_catalog

TOOL_CLI: Dict[str, str] = build_tool_cli_map()
CAPABILITY_HANDLERS: Dict[str, str] = build_capability_handlers()


def _handle_methyl_qc(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir:
        raise RuntimeError("methyl-qc task requires sampleDir in input_json")

    sample_path = Path(str(sample_dir))
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")

    project = input_json.get("project") or input_json.get("projectPath")
    from methyl_alignment_qc.core import process_samples_to_qc_jsons

    if project:
        from methyl_alignment_qc.project_resolver import resolve_alignment_qc_config

        cfg = resolve_alignment_qc_config(str(project))
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
        import json
        import tempfile

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

    import json

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
    project = input_json.get("project") or input_json.get("projectPath")
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

    cfg, _sample_dirs, out_dir = resolve_fragmentomics_step_config(str(project))
    project_obj = load_project(str(project))
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


_SAMPLE_PREP_DOMAIN_ACTIONS = frozenset({
    "sample.download_fastq",
    "sample.parabricks_fq2bam",
    "sample.methyl_qc",
    "sample.fragmentomics",
    "sample.methyl_extract",
    "sample.qc_failed",
})


def _attach_domain_sample_ref(
    action_name: str, input_json: Dict[str, Any], result: HandlerResult
) -> HandlerResult:
    sample_id = input_json.get("sampleId")
    sample_dir = input_json.get("sampleDir")
    if not sample_id or not sample_dir:
        return result
    try:
        from methyl_domain.helpers import enrich_sample_prep_output
        from methyl_domain.types import MethylSampleRef, to_tagged_json

        existing = input_json.get("sample")
        if isinstance(existing, dict) and existing.get("$type") == "MethylSampleRef":
            sample = MethylSampleRef.model_validate(existing)
        else:
            sample = MethylSampleRef(sampleId=str(sample_id), sampleDir=str(sample_dir))
        updated = enrich_sample_prep_output(action_name, sample, result)
        out = dict(result)
        out["domainSample"] = to_tagged_json(updated)
        return out
    except Exception:
        logger.debug("domain sample enrichment skipped for %s", action_name, exc_info=True)
        return result


def execute_task(capability: str, action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    """Run one ACTION and return output_json for sp_worker_submit_result."""
    entry = find_catalog_entry(action_name) or find_catalog_entry_by_capability(capability)
    if entry is None:
        raise RuntimeError(f"Unknown action {action_name!r} / capability {capability!r}")

    action = build_action_from_catalog(entry, sys.modules[__name__])
    result = action.execute(input_json)

    if action_name in _SAMPLE_PREP_DOMAIN_ACTIONS:
        result = _attach_domain_sample_ref(action_name, input_json, result)
    return result
