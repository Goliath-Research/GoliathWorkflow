"""Dispatch workflow ACTION tasks to catalog-defined CLI or in-process executors."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

Handler = Callable[[str, str, BaseModel], BaseModel]

from .action_execution import ActionExecutionResult, finalize_output
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


from .handler_helpers import (
    guardrails_from_payload,
    methyl_qc_result_code,
    qc_history_from_payload,
    screening_from_payload,
)
from .task_models.runtime_models import TaskRuntimeContext
from .task_models.sample_prep_models import MethylQcTaskOutput


def _resolve_reference_fasta(input_json: Dict[str, Any]) -> str:
    from methyl_utils.action_config_resolver import resolve_from_task_input

    project = input_json.get("projectPath") or input_json.get("project")
    regulatory: Dict[str, Any] = {}
    if project:
        from methyl_utils import load_project

        regulatory = load_project(str(project)).get_regulatory_config()
    alignment_cfg = resolve_from_task_input("alignment_qc", input_json, regulatory=regulatory)
    methyl_cfg = resolve_from_task_input("methyl_extract", input_json, regulatory=regulatory)
    reference_raw = methyl_cfg.get("reference_fasta") or alignment_cfg.get("genome_fasta")
    if not reference_raw:
        raise RuntimeError(
            "reference genome is required in site reference_genome.fasta or "
            "profile/site actionConfig.alignment_qc / methyl_extract"
        )
    return str(reference_raw)


def _handle_methyl_qc(_capability: str, _action_name: str, input: BaseModel) -> MethylQcTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir:
        raise RuntimeError("methyl-qc task requires sampleDir in input_json")

    sample_path = Path(str(sample_dir))
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")

    project = input_json.get("project") or input_json.get("projectPath")
    from methyl_alignment_qc.core import process_samples_to_qc_jsons
    from methyl_alignment_qc.core.qc_write_context import QcWriteContext

    write_ctx = QcWriteContext.from_input_json(input_json)
    write_ctx.sample_prep_log_path = str(sample_path / f"{sample_path.name}.sample_prep_log.jsonl")

    def _build_result(qc_path: Path) -> MethylQcTaskOutput:
        from .sample_prep_log import append_sample_prep_log

        payload = json.loads(qc_path.read_text(encoding="utf-8"))
        guardrails_raw = payload.get("guardrails") or {}
        guardrails = guardrails_from_payload(guardrails_raw if isinstance(guardrails_raw, dict) else {})
        screening_raw = guardrails_raw.get("screening") or {}
        screening = screening_from_payload(screening_raw if isinstance(screening_raw, dict) else {})
        qc_history = qc_history_from_payload(payload.get("qc_history") or [])
        tf1 = screening.trim_front1
        tt1 = screening.trim_tail1
        tf2 = screening.trim_front2
        tt2 = screening.trim_tail2
        disposition = str(screening.disposition or "")
        remediate = disposition == "REALIGN_TRIM" and any((tf1, tt1, tf2, tt2))
        remediate_r2 = bool(remediate and tf2 > 0 and tf1 == 0 and tt1 == 0 and tt2 == 0)
        rc = methyl_qc_result_code(remediate=remediate)
        append_sample_prep_log(
            sample_path,
            sample_id=sample_id or sample_path.name,
            action="sample.methyl_qc",
            capability=_capability,
            attempt=write_ctx.attempt,
            reason=write_ctx.attempt_reason,
            inputs={
                "qcAttempt": write_ctx.attempt,
                "alignmentPass": write_ctx.alignment_pass,
            },
            outputs={
                "qcPath": str(qc_path),
                "overallPass": guardrails.overall_pass,
                "disposition": screening.disposition,
                "result_code": rc,
            },
            result_code=rc,
            workflow_node_key=write_ctx.workflow_node_key or input_json.get("workflowNodeKey"),
        )
        return MethylQcTaskOutput(
            status="ok",
            result_code=rc,
            sampleId=sample_id or sample_path.name,
            qcPath=str(qc_path),
            guardrails=guardrails,
            screening=screening,
            qcHistory=qc_history,
            remediateAlignment=remediate,
            remediateR2Trim=remediate_r2,
        )

    if project:
        from methyl_alignment_qc.project_resolver import resolve_alignment_qc_config

        cfg = resolve_alignment_qc_config(str(project))
        out_dir = cfg.output_dir
        qc_path = Path(out_dir) / f"{sample_path.name}.json"
        if qc_path.is_file():
            import json

            prior = json.loads(qc_path.read_text(encoding="utf-8"))
            history = prior.get("qc_history")
            if isinstance(history, list):
                write_ctx.prior_qc_history = [h for h in history if isinstance(h, dict)]
        process_samples_to_qc_jsons(
            [str(sample_path)],
            out_dir,
            validate_schema=cfg.validate_schema,
            fragmentomics=cfg.fragmentomics,
            bisulfite_conversion=cfg.bisulfite_conversion,
            cycle_screening=cfg.cycle_screening,
            optional_guardrails=cfg.optional_guardrails,
            alignment_guardrails=cfg.alignment_guardrails,
            write_context=write_ctx,
        )
        qc_path = Path(out_dir) / f"{sample_path.name}.json"
    else:
        import json
        import tempfile

        with tempfile.TemporaryDirectory(prefix="methyl-qc-") as tmp:
            out_dir = tmp
            process_samples_to_qc_jsons(
                [str(sample_path)],
                out_dir,
                write_context=write_ctx,
            )
            qc_path = Path(out_dir) / f"{sample_path.name}.json"
            return _build_result(qc_path)

    if not qc_path.is_file():
        raise RuntimeError(f"QC JSON not written: {qc_path}")

    return _build_result(qc_path)


def _handle_methyl_extraction_qc(
    _capability: str, _action_name: str, input: BaseModel
) -> "ExtractionQcTaskOutput":
    from .task_models.sample_prep_models import ExtractionQcTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("methyl-extraction-qc task requires sampleDir and sampleId in input_json")

    sample_path = Path(str(sample_dir))
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")

    from methyl_extraction_qc.core.writer import process_sample_extraction_qc
    from methyl_extraction_qc.models.config import ExtractionQCConfig
    from methyl_extraction_qc.project_resolver import resolve_extraction_qc_config

    project = input_json.get("project") or input_json.get("projectPath")
    if project:
        config = resolve_extraction_qc_config(project, sample_paths=[str(sample_path)])
    else:
        resolved = input_json.get("resolvedConfig")
        if isinstance(resolved, dict) and resolved.get("expected_chromosomes"):
            config = ExtractionQCConfig(
                expected_chromosomes=[str(item) for item in resolved["expected_chromosomes"]]
            )
        else:
            manifest_path = sample_path / f"{sample_id}.extraction_manifest.json"
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                per_chr = manifest.get("per_chromosome") or {}
                if isinstance(per_chr, dict) and per_chr:
                    config = ExtractionQCConfig(expected_chromosomes=[str(k) for k in per_chr.keys()])
                else:
                    config = None
            else:
                config = None
    qc_path = process_sample_extraction_qc(
        sample_path,
        str(sample_id),
        config=config,
    )

    from .sample_prep_log import append_sample_prep_log

    from .handler_helpers import guardrails_from_payload

    payload = json.loads(qc_path.read_text(encoding="utf-8"))
    guardrails_raw = payload.get("guardrails") or {}
    guardrails = guardrails_from_payload(guardrails_raw if isinstance(guardrails_raw, dict) else {})
    append_sample_prep_log(
        sample_path,
        sample_id=str(sample_id),
        action="sample.extraction_qc",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason="Post-extraction manifest guardrails",
        inputs={"manifestPath": str(sample_path / f"{sample_id}.extraction_manifest.json")},
        outputs={
            "qcPath": str(qc_path),
            "overallPass": guardrails.overall_pass,
        },
        workflow_node_key=input_json.get("workflowNodeKey") or "extraction_qc",
    )
    return ExtractionQcTaskOutput(
        status="ok",
        sampleId=str(sample_id),
        qcPath=str(qc_path),
        guardrails=guardrails,
        extraction_pass=guardrails.overall_pass,
    )


def _handle_methyl_fragmentomics(
    _capability: str, _action_name: str, input: BaseModel
):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from .task_models.sample_prep_models import FragmentomicsTaskOutput

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
    sample_summary = summary.get("samples", {}).get(sid, {}) if isinstance(summary, dict) else {}
    sample_out = Path(out_dir) / sid
    summary_path = None
    n_fragments = None
    for candidate in ("fragmentomics_summary.json", "summary.json"):
        p = sample_out / candidate
        if p.is_file():
            summary_path = str(p)
            break
    if isinstance(sample_summary, dict):
        n_fragments = sample_summary.get("n_fragments")
    return FragmentomicsTaskOutput(
        status="ok",
        sampleId=sid,
        outputDir=str(sample_out),
        n_fragments=n_fragments,
        summary_path=summary_path,
    )


def _normalize_validation_iteration_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map planner iteration dict onto ValidationIterationRef fields."""
    payload = dict(item)
    payload["run_id"] = str(payload.get("run_id") or payload.get("runId") or "")
    if payload.get("iteration") is not None:
        payload["iteration"] = int(payload["iteration"])
    elif payload.get("phase_index") is not None:
        payload["iteration"] = int(payload["phase_index"])
    else:
        payload["iteration"] = 0
    run_dir = payload.get("runDir") or payload.get("run_dir")
    if run_dir is not None:
        payload["runDir"] = str(run_dir)
    project_path = payload.get("projectPath") or payload.get("projectJson")
    if project_path is not None:
        payload["projectPath"] = str(project_path)
    return {
        "run_id": payload["run_id"],
        "iteration": int(payload.get("iteration") or 0),
        "runDir": str(run_dir) if run_dir is not None else None,
        "projectPath": str(project_path) if project_path is not None else None,
    }


def _handle_validation_plan_iterations(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    runtime: TaskRuntimeContext,
):
    from methyl_validation.workflow_planner import ValidationPlanRequest, plan_validation_context

    from .task_models.validation_models import ValidationIterationRef, ValidationPlanTaskOutput

    request = (
        input
        if isinstance(input, ValidationPlanRequest)
        else ValidationPlanRequest.model_validate(input.model_dump(mode="json"))
    )
    if not isinstance(runtime, TaskRuntimeContext):
        runtime = TaskRuntimeContext.from_wire({})

    context = plan_validation_context(request, profile_overrides=runtime.validationProfile)
    iterations = []
    for item in context.iterations:
        payload = item.model_dump(mode="json")
        iterations.append(
            ValidationIterationRef.model_validate(_normalize_validation_iteration_payload(payload))
        )
    return ValidationPlanTaskOutput(
        status="ok",
        projectPath=context.projectPath,
        n_iterations=len(iterations),
        iterations=iterations,
    )


def _handle_mark_failed(_capability: str, _action_name: str, input: BaseModel):
    from .task_models.sample_prep_models import MarkFailedTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")

    return MarkFailedTaskOutput(
        sampleId=input_json.get("sampleId"),
        sampleDir=input_json.get("sampleDir"),
        status="QC_FAILED",
        reason=input_json.get("reason") or "alignment_qc_failed",
    )


def _handle_download_fastq(_capability: str, _action_name: str, input: BaseModel) -> DownloadFastqTaskOutput:
    from .fastq_source import download_from_source
    from .task_models import DownloadFastqTaskInput, DownloadFastqTaskOutput

    task = input if isinstance(input, DownloadFastqTaskInput) else DownloadFastqTaskInput.model_validate(
        input.model_dump(mode="json")
    )
    dest = Path(str(task.sampleDir))
    fastq_files = download_from_source(task.fastqSource, dest)
    sample_id = task.sampleId or dest.name
    return DownloadFastqTaskOutput(
        status="ok",
        sampleId=sample_id,
        fastqFiles=fastq_files,
        n_files=len(fastq_files),
    )


def _handle_trim_fastq(_capability: str, _action_name: str, input: BaseModel) -> TrimFastqTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from .fastq_trim_runner import run_fastp_trim
    from .sample_prep_log import append_sample_prep_log
    from .task_models.sample_prep_models import TrimFastqTaskOutput

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.trim_fastq requires sampleDir and sampleId")
    reason = str(
        input_json.get("remediationReason")
        or input_json.get("qcAttemptReason")
        or "REALIGN_TRIM"
    )
    result = run_fastp_trim(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        input_json=input_json,
    )
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.trim_fastq",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason=reason,
        inputs={
            "trimFront1": result.get("trimFront1"),
            "trimTail1": result.get("trimTail1"),
            "trimFront2": result.get("trimFront2"),
            "trimTail2": result.get("trimTail2"),
            "sampleDir": str(sample_dir),
        },
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "trim_fastq",
    )
    return TrimFastqTaskOutput(status="ok", **result)


def _handle_parabricks_fq2bam(_capability: str, _action_name: str, input: BaseModel) -> ParabricksTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from .parabricks_runner import run_fq2bam_meth
    from .sample_prep_log import append_sample_prep_log
    from .task_models.sample_prep_models import ParabricksTaskOutput

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.parabricks_fq2bam requires sampleDir and sampleId")
    reference_fasta = _resolve_reference_fasta(input_json)

    result = run_fq2bam_meth(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        reference_fasta=reference_fasta,
        project=input_json.get("projectPath") or input_json.get("project"),
        input_json=input_json,
    )
    reason = str(input_json.get("remediationReason") or "")
    if input_json.get("forceRealign"):
        reason = reason or f"forceRealign after trim_front2={input_json.get('trimFront2', '?')}"
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.parabricks_fq2bam",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason=reason or "Parabricks fq2bam_meth alignment",
        inputs={
            "forceRealign": bool(input_json.get("forceRealign")),
            "alignmentPass": input_json.get("alignmentPass") or "initial",
        },
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "parabricks_fq2bam",
    )
    return ParabricksTaskOutput(status="ok", **result)


def _handle_delete_fastqs(_capability: str, _action_name: str, input: BaseModel) -> DeleteTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from .task_models.sample_prep_models import DeleteTaskOutput

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir:
        raise RuntimeError("sample.delete_fastqs requires sampleDir")
    sample_path = Path(str(sample_dir))
    removed = 0
    for pattern in ("*.fastq.gz", "*.fq.gz", "*.fastq", "*.fq"):
        for path in sample_path.glob(pattern):
            path.unlink(missing_ok=True)
            removed += 1
    return DeleteTaskOutput(
        status="ok",
        sampleId=sample_id or sample_path.name,
        deleted=True,
        n_files_removed=removed,
    )


def _handle_delete_bam(_capability: str, _action_name: str, input: BaseModel) -> DeleteTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from .task_models.sample_prep_models import DeleteTaskOutput

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.delete_bam requires sampleDir and sampleId")
    sample_path = Path(str(sample_dir))
    removed = 0
    for name in (f"{sample_id}.bam", f"{sample_id}.BAM", f"{sample_id}.json"):
        path = sample_path / name
        if path.is_file():
            path.unlink()
            removed += 1
    return DeleteTaskOutput(
        status="ok",
        sampleId=sample_id,
        deleted=True,
        n_files_removed=removed,
    )


def _handle_methyl_extract(_capability: str, _action_name: str, input: BaseModel):
    from .extract_runner import run_methyl_extract
    from .task_models.sample_prep_models import MethylExtractTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    project = input_json.get("project") or input_json.get("projectPath")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.methyl_extract requires sampleDir and sampleId")
    if not project:
        raise RuntimeError("sample.methyl_extract requires project")

    raw = run_methyl_extract(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        project=str(project),
        input_json=input_json,
    )
    h5_files = list(raw.get("h5Files") or [])
    return MethylExtractTaskOutput(
        status="ok",
        sampleId=str(raw.get("sampleId") or sample_id),
        h5Files=h5_files,
        n_h5_files=len(h5_files),
    )


def _handle_archive_sample(_capability: str, _action_name: str, input: BaseModel) -> ArchiveSampleTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from .sample_archive import archive_from_task_input
    from .sample_prep_log import append_sample_prep_log
    from .task_models.sample_prep_models import ArchiveSampleTaskOutput

    result = archive_from_task_input(input_json)
    sample_dir = input_json.get("sampleDir")
    sample_id = result.get("sampleId")
    if sample_dir and sample_id:
        append_sample_prep_log(
            Path(str(sample_dir)),
            sample_id=str(sample_id),
            action="sample.archive_sample",
            capability=_capability,
            attempt=int(input_json.get("qcAttempt") or 1),
            reason=str(input_json.get("rejectReason") or "Archive sample bundle to durable storage"),
            inputs={"mode": result.get("archiveMode"), "remotePrefix": result.get("remotePrefix")},
            outputs=result,
            workflow_node_key=input_json.get("workflowNodeKey") or "archive_sample",
        )
    return ArchiveSampleTaskOutput(status="ok", **result)


def _resolve_monte_carlo_runs_root(input_json: Dict[str, Any]) -> Path:
    project_path = input_json.get("projectPath") or input_json.get("project")
    if not project_path:
        raise RuntimeError("validation action requires projectPath")
    explicit = input_json.get("monteCarloRunsRoot")
    if explicit:
        return Path(str(explicit)).expanduser().resolve()
    from methyl_utils import load_project

    project = load_project(str(project_path))
    return Path(project.output_base) / project.project_name / "monte_carlo_runs"


def _load_mc_config(input_json: Dict[str, Any]):
    from methyl_validation.workflow_planner import ValidationPlanRequest, _load_config_from_project, resolve_base_project_json

    base_project = resolve_base_project_json(input_json.get("projectPath") or input_json.get("project"))
    request = ValidationPlanRequest.model_validate(input_json)
    return _load_config_from_project(base_project, request), base_project


def _handle_validation_stability(_capability: str, _action_name: str, input: BaseModel):
    input_json: Dict[str, Any] = input.model_dump(mode="json")

    from methyl_validation.stability import run_stability_analysis

    from .task_models.validation_models import StabilitySummary, ValidationStabilityOutput

    mc_root = _resolve_monte_carlo_runs_root(input_json)
    config, _base = _load_mc_config(input_json)
    output_dir = Path(input_json.get("outputDir") or mc_root / "stability")
    summary_raw = run_stability_analysis(
        mc_root,
        output_dir=output_dir,
        dmp_min_freq=config.stability_dmp_freq,
        gene_min_freq=config.stability_gene_freq,
        min_balanced_accuracy=config.stability_min_balanced_accuracy,
        prefer_classifier_panel_dmps=bool(config.stability_featurecuts_enabled),
        prefer_classifier_gene_panels=bool(config.stability_gene_featurecuts_enabled),
        dual_cutoff_enabled=bool(config.stability_dual_cutoff_enabled),
        relaxed_cutoff_mode=config.stability_relaxed_cutoff_mode,
        relaxed_multiplier=config.stability_relaxed_multiplier,
        score_eps=config.stability_score_eps,
        tiered_stability_enabled=bool(config.stability_tiers_enabled),
        tier_core_frequency=config.stability_tier_core_freq,
        tier_extended_frequency=config.stability_tier_extended_freq,
        tier_exploratory_frequency=config.stability_tier_exploratory_freq,
        default_freeze_tier=config.stability_default_freeze_tier,
    )
    summary_path = output_dir / "stability_summary.json"
    return ValidationStabilityOutput(
        status="ok",
        outputDir=str(output_dir),
        summary=StabilitySummary(
            n_iterations=summary_raw.get("n_iterations"),
            n_stable_dmps=summary_raw.get("n_stable_dmps"),
            n_stable_genes=summary_raw.get("n_stable_genes"),
            dmp_min_frequency=summary_raw.get("dmp_min_frequency"),
            gene_min_frequency=summary_raw.get("gene_min_frequency"),
            summary_json_path=str(summary_path) if summary_path.is_file() else None,
        ),
    )


def _handle_validation_biomarker_filter(
    _capability: str, _action_name: str, input: BaseModel
):
    """In-process PPI-only biomarker gene pool filter on mapper combined genes."""
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from pathlib import Path

    import pandas as pd

    from methyl_gene_select.core.gene_featurecuts import _apply_biomarker_gene_pool_filter
    from methyl_worker.split_detector_task_models import BiomarkerFilterSummary, BiomarkerFilterTaskOutput

    project_path = input_json.get("projectPath") or input_json.get("project")
    if not project_path:
        raise RuntimeError("validation.biomarker_filter requires projectPath")
    run_dir = Path(str(input_json.get("runDir") or project_path)).resolve()
    config, _base = _load_mc_config(input_json)
    mapper_dirs = list(run_dir.glob("**/mapper/*/*")) or list(run_dir.glob("mapper/*/*"))
    gene_df = None
    for d in mapper_dirs:
        for csv in d.glob("all-gene_name-combined.csv"):
            try:
                gene_df = pd.read_csv(csv)
                break
            except Exception:
                continue
        if gene_df is not None:
            break
    if gene_df is None or gene_df.empty:
        raise RuntimeError("No mapper all-gene_name-combined.csv found for biomarker filter")
    out_dir = run_dir / "gene_stability"
    filtered, meta = _apply_biomarker_gene_pool_filter(
        gene_df,
        project_json=Path(str(project_path)),
        config=config,
        out_dir=out_dir,
    )
    out_csv = out_dir / "biomarker_gene_pool.csv"
    filtered.to_csv(out_csv, index=False)
    summary = BiomarkerFilterSummary.model_validate(meta)
    return BiomarkerFilterTaskOutput(
        status="ok",
        n_genes=int(len(filtered)),
        outputCsv=str(out_csv),
        biomarker_filter=summary,
    )


def _handle_validation_prepare_freeze(
    _capability: str, _action_name: str, input: BaseModel
):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from methyl_validation.stability import prepare_freeze_project

    from .task_models.validation_models import ValidationPrepareFreezeOutput

    config, base_project = _load_mc_config(input_json)
    mc_root = _resolve_monte_carlo_runs_root(input_json)
    stable_csv = input_json.get("stableDmpCsv") or config.freeze_stable_dmp_csv or str(
        mc_root / "stability" / "stable_dmps_production.csv"
    )
    result = prepare_freeze_project(
        base_project=base_project,
        stable_dmp_csv=str(stable_csv),
        monte_carlo_runs_root=mc_root,
        production_output_dir=input_json.get("productionOutputDir") or config.production_output_dir,
        config=config,
    )
    return ValidationPrepareFreezeOutput(
        status="ok",
        productionOutputDir=result.get("productionOutputDir") or result.get("production_output_dir"),
        sourceRunDir=result.get("sourceRunDir"),
        targetRunDir=result.get("targetRunDir"),
        projectPath=result.get("projectPath") or str(base_project),
    )


def _handle_validation_stability_freeze_readiness(
    _capability: str, _action_name: str, input: BaseModel
):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from methyl_validation.stability_freeze_readiness import analyze_project_root

    from .task_models.validation_models import ValidationFreezeReadinessOutput

    project_path = input_json.get("projectPath") or input_json.get("project")
    if not project_path:
        raise RuntimeError("validation.stability_freeze_readiness requires projectPath")
    from methyl_utils import load_project

    project = load_project(str(project_path))
    project_root = Path(project.output_base) / project.project_name
    report = analyze_project_root(project_root)
    verdict = report.get("verdict", {}) if isinstance(report, dict) else {}
    missing = verdict.get("missing_artifacts") or verdict.get("missing") or []
    if not isinstance(missing, list):
        missing = []
    ready = str(verdict.get("ready", verdict.get("status", ""))).lower() in {"ready", "pass", "true", "ok"}
    return ValidationFreezeReadinessOutput(
        status="ok",
        ready=ready,
        outputDir=str(project_root),
        missing_artifacts=[str(x) for x in missing],
    )


def _handle_validation_link_artifacts(
    _capability: str, _action_name: str, input: BaseModel
):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from methyl_validation.project_gen import link_run_artifacts_from_source

    from .task_models.validation_models import ValidationLinkArtifactsOutput

    source = input_json.get("sourceRunDir")
    target = input_json.get("targetRunDir") or input_json.get("runDir")
    if not source or not target:
        raise RuntimeError("validation.link_artifacts requires sourceRunDir and targetRunDir")
    linked = link_run_artifacts_from_source(source, target)
    return ValidationLinkArtifactsOutput(
        status="ok",
        bundleDir=str(linked.get("targetRunDir") or target),
        linked_files=[str(x) for x in (linked.get("linked") or [])],
    )


def _handle_validation_model_bundle(
    _capability: str, _action_name: str, input: BaseModel
):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from methyl_validation.model_bundle import build_model_feature_bundle

    from .task_models.validation_models import ValidationModelBundleOutput

    project_path = input_json.get("projectPath") or input_json.get("project")
    if not project_path:
        raise RuntimeError("validation.model_bundle requires projectPath")
    bundle_dir = Path(input_json.get("bundleDir") or Path(str(project_path)).parent / "model_bundle")
    manifest = build_model_feature_bundle(str(project_path), bundle_dir)
    bundle_h5 = bundle_dir / "model_feature_bundle.h5"
    return ValidationModelBundleOutput(
        status="ok",
        bundleDir=str(bundle_dir),
        bundleH5=str(bundle_h5) if bundle_h5.is_file() else str(manifest),
    )


def _handle_validation_model_train(
    _capability: str, _action_name: str, input: BaseModel
):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from .task_models.validation_models import ValidationModelTrainOutput

    backend = str(input_json.get("backend") or "tabular_sklearn")
    project_path = Path(input_json.get("projectPath") or input_json.get("project") or "")
    if not project_path.is_file():
        raise RuntimeError("validation.model_train requires projectPath")
    run_dir = Path(input_json.get("runDir") or project_path.parent)
    bundle_h5 = input_json.get("bundleH5") or run_dir / "model_bundle" / "model_feature_bundle.h5"
    output_dir = Path(input_json.get("outputDir") or run_dir / "models")
    output_dir.mkdir(parents=True, exist_ok=True)
    if backend == "tabular_sklearn":
        from methyl_validation.tabular_backend import train_tabular_model

        summary = train_tabular_model(project_path, bundle_h5, output_dir)
    elif backend == "generative_hybrid":
        from methyl_validation.generative_backend import train_generative_model

        summary = train_generative_model(project_path, bundle_h5, output_dir)
    else:
        raise RuntimeError(
            f"validation.model_train does not support backend={backend!r}; use pipeline.classifier for ecdf"
        )
    model_path = str(summary) if not isinstance(summary, dict) else summary.get("model_path")
    if model_path is None:
        candidate = output_dir / "tabular-model.joblib"
        model_path = str(candidate) if candidate.is_file() else str(output_dir)
    return ValidationModelTrainOutput(
        status="ok",
        model_path=str(model_path),
        backend=backend,
    )


def _handle_validation_model_predict(
    _capability: str, _action_name: str, input: BaseModel
):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from .task_models.validation_models import ValidationModelPredictOutput

    backend = str(input_json.get("backend") or "tabular_sklearn")
    project_path = Path(input_json.get("projectPath") or input_json.get("project") or "")
    if not project_path.is_file():
        raise RuntimeError("validation.model_predict requires projectPath")
    run_dir = Path(input_json.get("runDir") or project_path.parent)
    if backend == "tabular_sklearn":
        from methyl_validation.tabular_backend import predict_tabular_model_from_project

        model_dir = run_dir / "models"
        summary = predict_tabular_model_from_project(project_path, model_dir, run_dir)
    elif backend == "generative_hybrid":
        from methyl_validation.generative_backend import predict_generative_model_from_project

        summary = predict_generative_model_from_project(project_path, output_dir=run_dir)
    else:
        raise RuntimeError(
            f"validation.model_predict does not support backend={backend!r}; use pipeline.predictor for ecdf"
        )
    predictions_path = run_dir / "predictions.csv"
    n_samples = None
    if isinstance(summary, dict):
        n_samples = summary.get("n_samples")
    if n_samples is None and predictions_path.is_file():
        try:
            import pandas as pd

            n_samples = len(pd.read_csv(predictions_path))
        except Exception:
            n_samples = None
    return ValidationModelPredictOutput(
        status="ok",
        predictions_path=str(predictions_path) if predictions_path.is_file() else None,
        n_samples=int(n_samples) if n_samples is not None else None,
    )


def _handle_validation_model_mc(
    _capability: str, _action_name: str, input: BaseModel
):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from methyl_validation.model_mc_runner import run_model_mc_all

    from .task_models.validation_models import ValidationModelMcOutput

    config, _base = _load_mc_config(input_json)
    mc_root = _resolve_monte_carlo_runs_root(input_json)
    production_dir = Path(
        input_json.get("productionOutputDir") or config.production_output_dir or mc_root / "production"
    )
    production_project = production_dir / "project.json"
    backends = input_json.get("backends")
    resume = input_json.get("resume")
    raw = run_model_mc_all(
        production_project=production_project,
        monte_carlo_runs_root=mc_root,
        config=config,
        backends=list(backends) if backends else None,
        resume=int(resume) if resume is not None else None,
    )
    return ValidationModelMcOutput(
        status="ok",
        modelMcRoot=str(raw.get("modelMcRoot") or mc_root / "model_mc"),
        n_iterations=int(raw.get("nSharedIterations") or 0),
    )


def _handle_validation_select_best_model(
    _capability: str, _action_name: str, input: BaseModel
):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from methyl_validation.cli import _write_backend_ranking
    from methyl_validation.stability import build_production_model

    from .task_models.validation_models import ValidationSelectBestModelOutput

    config, _base = _load_mc_config(input_json)
    mc_root = _resolve_monte_carlo_runs_root(input_json)
    model_mc_root = Path(input_json.get("modelMcRoot") or mc_root / "model_mc")
    backends = list(input_json.get("backends") or ["ecdf", "tabular_sklearn", "generative_hybrid"])
    metric = str(input_json.get("selectionMetric") or "balanced_accuracy")
    stat = str(input_json.get("selectionStat") or "median")
    ranking = _write_backend_ranking(model_mc_root, backends, metric=metric, stat=stat)
    best_backend = str(ranking[0]["backend"])
    summary = build_production_model(
        monte_carlo_runs_root=mc_root,
        production_output_dir=config.production_output_dir,
        config=config.with_backend_selection(best_backend),
    )
    production_dir = Path(summary.get("output_dir") or mc_root / "production")
    selection_path = production_dir / "selected_backend.json"
    selection_payload = {
        "selected_backend": best_backend,
        "selection_metric": metric,
        "selection_stat": stat,
        "ranking": ranking,
    }
    selection_path.write_text(json.dumps(selection_payload, indent=2) + "\n", encoding="utf-8")
    selection_stat = ranking[0].get(stat) if ranking else None
    return ValidationSelectBestModelOutput(
        status="ok",
        selectedBackend=best_backend,
        selectionMetric=metric,
        selectionStat=float(selection_stat) if selection_stat is not None else None,
    )


def _handle_validation_post_model_validation(
    _capability: str, _action_name: str, input: BaseModel
):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from methyl_validation.pipeline_runner import (
        run_post_model_validation_binary,
        run_post_model_validation_multiclass,
    )
    from methyl_validation.project_gen import infer_monte_carlo_layout

    from .task_models.validation_models import ValidationPostModelValidationOutput

    config, base_project = _load_mc_config(input_json)
    mc_root = _resolve_monte_carlo_runs_root(input_json)
    production_dir = Path(
        input_json.get("productionOutputDir") or config.production_output_dir or mc_root / "production"
    )
    production_project = production_dir / "project.json"
    if not production_project.is_file():
        raise RuntimeError(f"production project not found: {production_project}")
    layout = infer_monte_carlo_layout(production_project, len(config.cohorts))
    run_dir = Path(input_json.get("runDir") or mc_root / "post_model_validation" / "run_0001")
    run_dir.mkdir(parents=True, exist_ok=True)
    if layout == "binary":
        success, errors, timings = run_post_model_validation_binary(
            production_project,
            run_dir,
            logs_dir=run_dir / "logs",
            config=config,
        )
    else:
        success, errors, timings = run_post_model_validation_multiclass(
            production_project,
            run_dir,
            logs_dir=run_dir / "logs",
            config=config,
        )
    report_path = run_dir / "post_model_validation_report.json"
    if not report_path.is_file():
        report_path.write_text(
            json.dumps({"success": success, "errors": errors, "timings": timings}, indent=2),
            encoding="utf-8",
        )
    return ValidationPostModelValidationOutput(
        status="ok" if success else "failed",
        result_code=0 if success else 1,
        outputDir=str(run_dir),
        report_path=str(report_path),
        passed=success,
    )


def _stub_external_enabled() -> bool:
    return os.environ.get("WORKER_STUB_EXTERNAL", "").lower() in {"1", "true", "yes"}


def _write_stub_extract_artifacts(sample_path: Path, sample_id: str) -> list[str]:
    h5_name = "21-CG.h5"
    h5_path = sample_path / h5_name
    if not h5_path.is_file():
        h5_path.write_bytes(b"stub-h5")
    manifest_path = sample_path / f"{sample_id}.extraction_manifest.json"
    if not manifest_path.is_file():
        manifest_path.write_text(
            json.dumps(
                {
                    "metadata": {
                        "schema_name": "methylextractor.extraction_manifest",
                        "schema_version": "1.0.0",
                        "contexts_extracted": ["CG"],
                    },
                    "summary": {"cpg_weighted_mean_coverage": 20.0},
                    "per_chromosome": {"21": {"CG": {"mean_coverage": 18.0}}},
                }
            ),
            encoding="utf-8",
        )
    return [h5_name]


def _handle_stub_external(capability: str, _action_name: str, input: BaseModel) -> BaseModel:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    if not _stub_external_enabled():
        raise RuntimeError(
            f"No local handler for capability {capability!r}. "
            "Implement a domain worker or set WORKER_STUB_EXTERNAL=1 for dry-run."
        )

    from .task_models.sample_prep_models import (
        ArchiveSampleTaskOutput,
        DeleteTaskOutput,
        DownloadFastqTaskOutput,
        ExtractionQcTaskOutput,
        FragmentomicsTaskOutput,
        MarkFailedTaskOutput,
        MethylExtractTaskOutput,
        MethylQcTaskOutput,
        ParabricksTaskOutput,
        TrimFastqTaskOutput,
    )

    logger.warning("WORKER_STUB_EXTERNAL: faking success for %s", capability)
    sample_id = str(input_json.get("sampleId", "unknown"))
    sample_dir = str(input_json.get("sampleDir", ""))
    sample_path = Path(sample_dir) if sample_dir else None

    if capability == "sample.download-fastq":
        if sample_path is not None:
            sample_path.mkdir(parents=True, exist_ok=True)
            for suffix in ("_1.fastq.gz", "_2.fastq.gz"):
                fq = sample_path / f"{sample_id}{suffix}"
                if not fq.is_file():
                    fq.touch()
        files = [f"{sample_id}_1.fastq.gz", f"{sample_id}_2.fastq.gz"]
        return DownloadFastqTaskOutput(
            status="ok",
            sampleId=sample_id,
            fastqFiles=files,
            n_files=len(files),
        )
    if capability == "parabricks.fq2bam":
        bam = f"{sample_dir}/{sample_id}.bam" if sample_dir else f"{sample_id}.bam"
        if sample_path is not None:
            sample_path.mkdir(parents=True, exist_ok=True)
            Path(bam).touch(exist_ok=True)
            metrics = sample_path / f"{sample_id}.json"
            if not metrics.is_file():
                metrics.write_text('{"guardrails": {"overall_pass": true}}', encoding="utf-8")
        return ParabricksTaskOutput(
            status="ok",
            sampleId=sample_id,
            bamPath=bam,
            metricsJson=f"{sample_dir}/{sample_id}.json" if sample_dir else f"{sample_id}.json",
            qcMetricsTar=(
                f"{sample_dir}/{sample_id}.qc-metrics.tar" if sample_dir else f"{sample_id}.qc-metrics.tar"
            ),
        )
    if capability == "sample.delete-fastqs":
        return DeleteTaskOutput(status="ok", sampleId=sample_id, deleted=True, n_files_removed=0)
    if capability == "sample.trim-fastq":
        return TrimFastqTaskOutput(
            status="ok",
            sampleId=sample_id,
            trimFront2=str(input_json.get("trimFront2", 5)),
            trimmedR1=f"{sample_dir}/{sample_id}_1.trimmed.fastq.gz",
            trimmedR2=f"{sample_dir}/{sample_id}_2.trimmed.fastq.gz",
        )
    if capability == "sample.delete-bam":
        return DeleteTaskOutput(status="ok", sampleId=sample_id, deleted=True, n_files_removed=0)
    if capability == "methyl-extract":
        h5_files = ["21-CG.h5"]
        if sample_path is not None:
            h5_files = _write_stub_extract_artifacts(sample_path, sample_id)
        return MethylExtractTaskOutput(
            status="ok",
            sampleId=sample_id,
            h5Files=h5_files,
            n_h5_files=len(h5_files),
        )
    if capability == "sample.archive-sample":
        return ArchiveSampleTaskOutput(
            status="ok",
            sampleId=sample_id,
            archiveMode=str(input_json.get("mode") or "full"),
            uploadedFiles=["21-CG.h5"],
            skippedFiles=[],
            remotePrefix="studies/test/",
            uploadedCount=1,
            skippedCount=0,
            sampleArchived=True,
        )
    if capability == "methyl-qc":
        from .handler_helpers import guardrails_from_payload, screening_from_payload

        qc_path = f"{sample_dir}/{sample_id}.qc.json" if sample_dir else f"{sample_id}.qc.json"
        guardrails = guardrails_from_payload({"overall_pass": True})
        screening = screening_from_payload(
            {
                "disposition": "PASS",
                "trim_front1": 0,
                "trim_tail1": 0,
                "trim_front2": 0,
                "trim_tail2": 0,
                "message": "stub pass",
            }
        )
        return MethylQcTaskOutput(
            status="ok",
            result_code=0,
            sampleId=sample_id,
            qcPath=qc_path,
            guardrails=guardrails,
            screening=screening,
            qcHistory=[],
            remediateAlignment=False,
            remediateR2Trim=False,
        )
    if capability == "methyl-fragmentomics":
        return FragmentomicsTaskOutput(
            status="ok",
            sampleId=sample_id,
            outputDir=sample_dir or "/tmp",
        )
    if capability == "methyl-extraction-qc":
        from .handler_helpers import guardrails_from_payload

        return ExtractionQcTaskOutput(
            status="ok",
            sampleId=sample_id,
            qcPath=f"{sample_dir}/{sample_id}.extraction_qc.json" if sample_dir else f"{sample_id}.extraction_qc.json",
            guardrails=guardrails_from_payload({"overall_pass": True}),
            extraction_pass=True,
        )
    if capability == "sample.mark-failed":
        return MarkFailedTaskOutput(
            sampleId=sample_id,
            status="QC_FAILED",
            reason=str(input_json.get("reason") or "alignment_qc_failed"),
        )
    raise RuntimeError(
        f"WORKER_STUB_EXTERNAL=1 has no stub for capability {capability!r}."
    )


_SAMPLE_PREP_DOMAIN_ACTIONS = frozenset({
    "sample.download_fastq",
    "sample.parabricks_fq2bam",
    "sample.trim_fastq",
    "sample.methyl_qc",
    "sample.fragmentomics",
    "sample.methyl_extract",
    "sample.extraction_qc",
    "sample.archive_sample",
    "sample.qc_failed",
})


_STUB_EXTERNAL_CAPABILITIES = frozenset({
    "sample.download-fastq",
    "parabricks.fq2bam",
    "sample.delete-fastqs",
    "sample.trim-fastq",
    "sample.delete-bam",
    "methyl-extract",
    "sample.archive-sample",
    "methyl-qc",
    "methyl-fragmentomics",
    "methyl-extraction-qc",
    "sample.mark-failed",
})


def _attach_domain_sample_ref(
    entry,
    action_name: str,
    input_json: Dict[str, Any],
    result: ActionExecutionResult,
) -> ActionExecutionResult:
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
        payload = result.output.model_dump(mode="json")
        updated = enrich_sample_prep_output(action_name, sample, payload)
        merged = {**payload, "domainSample": to_tagged_json(updated)}
        from methyl_domain.action_result import utc_now

        started = getattr(result.output, "started_at_utc", None) or utc_now()
        finished = getattr(result.output, "finished_at_utc", None) or utc_now()
        duration = getattr(result.output, "duration_ms", None) or 0
        exit_code = getattr(result.output, "exit_code", None) or 0
        manifest = getattr(result.output, "manifest_path", None)
        output = finalize_output(
            entry,
            merged,
            started_at=started,
            finished_at=finished,
            duration_ms=duration,
            exit_code=exit_code,
            manifest_path=manifest,
        )
        return ActionExecutionResult(result_code=result.result_code, output=output)
    except Exception:
        logger.debug("domain sample enrichment skipped for %s", action_name, exc_info=True)
        return result


def execute_task(capability: str, action_name: str, input_json: Dict[str, Any]) -> ActionExecutionResult:
    """Run one ACTION and return typed output + branch result_code for sp_worker_submit_result."""
    entry = find_catalog_entry(action_name) or find_catalog_entry_by_capability(capability)
    if entry is None:
        raise RuntimeError(f"Unknown action {action_name!r} / capability {capability!r}")

    from .action_execution import validate_input
    from .action_skip import maybe_skip_action, record_action_execution
    from .task_validation import extract_runtime_input, merge_runtime_input, strip_runtime_input

    runtime = extract_runtime_input(input_json)
    task_input = strip_runtime_input(input_json)
    input_model = validate_input(entry, task_input)
    skip_input = merge_runtime_input(task_input, runtime)

    skipped_result = maybe_skip_action(entry, skip_input)
    if skipped_result is not None:
        _log_action_execution(
            entry, action_name, skip_input, skipped_result, skipped=True, input_model=input_model
        )
        if action_name in _SAMPLE_PREP_DOMAIN_ACTIONS:
            skipped_result = _attach_domain_sample_ref(entry, action_name, task_input, skipped_result)
        return skipped_result

    if _stub_external_enabled() and capability in _STUB_EXTERNAL_CAPABILITIES:
        from .action_execution import ExecutionTimer, execution_result_from_output

        timer = ExecutionTimer()
        output_model = _handle_stub_external(capability, action_name, input_model)
        finished_at, duration_ms = timer.finish()
        output = finalize_output(
            entry,
            output_model.model_dump(mode="json"),
            started_at=timer.started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
        )
        result = execution_result_from_output(output)
    else:
        action = build_action_from_catalog(entry, sys.modules[__name__])
        result = action.execute(skip_input)

    record_action_execution(entry, skip_input, input_model, result, skipped=False)
    if action_name in _SAMPLE_PREP_DOMAIN_ACTIONS:
        result = _attach_domain_sample_ref(entry, action_name, task_input, result)
    _log_action_execution(entry, action_name, skip_input, result, skipped=False, input_model=input_model)
    return result


def _log_action_execution(
    entry,
    action_name: str,
    input_json: Dict[str, Any],
    result: ActionExecutionResult,
    *,
    skipped: bool,
    input_model: Optional[BaseModel] = None,
) -> None:
    if entry.category != "validation":
        return
    try:
        from .action_run_log import append_action_run_log
        from .action_skip import (
            compute_action_revision,
            compute_input_signature,
            compute_output_signature,
            artifacts_from_output,
        )

        mc_root = _resolve_monte_carlo_runs_root(input_json)
        if mc_root is None:
            return
        run_dir = input_json.get("runDir") or input_json.get("targetRunDir")
        outputs = result.output.model_dump(mode="json")
        trimmed_inputs = {
            k: input_json[k]
            for k in ("projectPath", "project", "runDir", "monteCarloRunsRoot", "outputDir")
            if k in input_json
        }
        if input_model is None:
            from .action_execution import validate_input

            input_model = validate_input(entry, input_json)
        artifacts = artifacts_from_output(outputs)
        append_action_run_log(
            mc_root,
            action=action_name,
            capability=entry.capability,
            result_code=result.result_code,
            run_dir=str(run_dir) if run_dir else None,
            inputs=trimmed_inputs,
            outputs=outputs,
            workflow_node_key=input_json.get("workflowNodeKey"),
            skipped=skipped,
            skip_reason="signature_match" if skipped else None,
            action_revision=compute_action_revision(entry),
            input_signature=compute_input_signature(entry, input_json, input_model),
            output_signature=compute_output_signature(artifacts),
        )
    except Exception:
        logger.debug("validation action_run_log append skipped for %s", action_name, exc_info=True)
