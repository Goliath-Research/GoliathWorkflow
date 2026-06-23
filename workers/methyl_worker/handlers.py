"""Dispatch workflow ACTION tasks to catalog-defined CLI or in-process executors."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
    from methyl_alignment_qc.core.qc_write_context import QcWriteContext

    write_ctx = QcWriteContext.from_input_json(input_json)
    write_ctx.sample_prep_log_path = str(sample_path / f"{sample_path.name}.sample_prep_log.jsonl")

    def _build_result(qc_path: Path) -> HandlerResult:
        import json

        from .sample_prep_log import append_sample_prep_log

        payload = json.loads(qc_path.read_text(encoding="utf-8"))
        guardrails = payload.get("guardrails") or {}
        screening = guardrails.get("screening") or {}
        qc_history = payload.get("qc_history") or []
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
                "overallPass": guardrails.get("overall_pass"),
                "disposition": screening.get("disposition"),
            },
            workflow_node_key=write_ctx.workflow_node_key or input_json.get("workflowNodeKey"),
        )
        return {
            "sampleId": sample_id or sample_path.name,
            "qcPath": str(qc_path),
            "guardrails": guardrails,
            "screening": screening,
            "qcHistory": qc_history,
            "remediateR2Trim": bool(
                screening.get("disposition") == "REALIGN_READ2_TRIM"
                and int(screening.get("trim_front2") or 0) > 0
            ),
        }

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
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
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
    chromosomes = input_json.get("chromosomes")
    if project:
        config = resolve_extraction_qc_config(project, sample_paths=[str(sample_path)])
    elif chromosomes:
        config = ExtractionQCConfig(expected_chromosomes=[str(item) for item in chromosomes])
    else:
        config = None
    qc_path = process_sample_extraction_qc(
        sample_path,
        str(sample_id),
        config=config,
    )

    import json

    from .sample_prep_log import append_sample_prep_log

    payload = json.loads(qc_path.read_text(encoding="utf-8"))
    guardrails = payload.get("guardrails") or {}
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
            "overallPass": guardrails.get("overall_pass"),
        },
        workflow_node_key=input_json.get("workflowNodeKey") or "extraction_qc",
    )
    return {
        "sampleId": str(sample_id),
        "qcPath": str(qc_path),
        "guardrails": guardrails,
        "extractionQc": {
            "qcPath": str(qc_path),
            "overallPass": bool(guardrails.get("overall_pass", False)),
            "guardrails": guardrails,
        },
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


def _handle_download_fastq(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    from .fastq_source import download_from_source
    from .task_models import DownloadFastqTaskInput

    task = DownloadFastqTaskInput.model_validate(input_json)
    dest = Path(str(task.sampleDir))
    fastq_files = download_from_source(task.fastqSource, dest)
    return {"sampleId": task.sampleId or dest.name, "fastqFiles": fastq_files}


def _handle_trim_fastq(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    from .fastq_trim_runner import run_fastp_trim_front2
    from .sample_prep_log import append_sample_prep_log

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    trim_front2 = input_json.get("trimFront2")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.trim_fastq requires sampleDir and sampleId")
    if trim_front2 is None:
        raise RuntimeError("sample.trim_fastq requires trimFront2")
    trim_n = int(trim_front2)
    reason = str(
        input_json.get("remediationReason")
        or input_json.get("qcAttemptReason")
        or f"REALIGN_READ2_TRIM: trim_front2={trim_n}"
    )
    result = run_fastp_trim_front2(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        trim_front2=trim_n,
        input_json=input_json,
    )
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.trim_fastq",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason=reason,
        inputs={"trimFront2": trim_n, "sampleDir": str(sample_dir)},
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "trim_fastq",
    )
    return result


def _handle_parabricks_fq2bam(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    from .parabricks_runner import run_fq2bam_meth
    from .sample_prep_log import append_sample_prep_log

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    reference_fasta = input_json.get("referenceFasta")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.parabricks_fq2bam requires sampleDir and sampleId")
    if not reference_fasta:
        raise RuntimeError("sample.parabricks_fq2bam requires referenceFasta")

    result = run_fq2bam_meth(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        reference_fasta=str(reference_fasta),
        project=input_json.get("projectPath") or input_json.get("project"),
        input_json=input_json,
        parabricks_image=input_json.get("parabricksImage"),
        bwa_threads=input_json.get("bwaThreads"),
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
    return result


def _handle_delete_fastqs(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
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
    return {"sampleId": sample_id or sample_path.name, "deleted": True, "removedCount": removed}


def _handle_delete_bam(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
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
    return {"sampleId": sample_id, "deleted": True, "removedCount": removed}


def _handle_methyl_extract(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    from .extract_runner import run_methyl_extract

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    project = input_json.get("project") or input_json.get("projectPath")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.methyl_extract requires sampleDir and sampleId")
    if not project:
        raise RuntimeError("sample.methyl_extract requires project")

    return run_methyl_extract(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        project=str(project),
        input_json=input_json,
    )


def _handle_upload_h5(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    from .h5_upload import upload_from_task_input
    from .sample_prep_log import append_sample_prep_log

    result = upload_from_task_input(input_json)
    sample_dir = input_json.get("sampleDir")
    sample_id = result.get("sampleId")
    if sample_dir and sample_id:
        append_sample_prep_log(
            Path(str(sample_dir)),
            sample_id=str(sample_id),
            action="sample.upload_h5",
            capability=_capability,
            attempt=int(input_json.get("qcAttempt") or 1),
            reason="Archive methylation HDF5 to durable storage",
            inputs={"remotePrefix": result.get("remotePrefix")},
            outputs=result,
            workflow_node_key=input_json.get("workflowNodeKey") or "upload_h5",
        )
    return result


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


def _handle_validation_stability(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    from methyl_validation.stability import run_stability_analysis

    mc_root = _resolve_monte_carlo_runs_root(input_json)
    config, _base = _load_mc_config(input_json)
    output_dir = Path(input_json.get("outputDir") or mc_root / "stability")
    summary = run_stability_analysis(
        mc_root,
        output_dir=output_dir,
        dmp_min_freq=config.stability_dmp_min_frequency,
        gene_min_freq=config.stability_gene_min_frequency,
        top_n_dmps=config.stability_top_n_dmps,
        min_balanced_accuracy=config.stability_min_balanced_accuracy,
        prefer_classifier_panel_dmps=config.stability_prefer_classifier_panel_dmps,
        prefer_classifier_gene_panels=config.stability_prefer_classifier_gene_panels,
        dual_cutoff_enabled=config.stability_dual_cutoff_enabled,
        relaxed_cutoff_mode=config.stability_relaxed_cutoff_mode,
        relaxed_multiplier=config.stability_relaxed_multiplier,
        tiered_stability_enabled=config.stability_tiered_enabled,
        tier_core_frequency=config.stability_tier_core_frequency,
        tier_extended_frequency=config.stability_tier_extended_frequency,
        tier_exploratory_frequency=config.stability_tier_exploratory_frequency,
        default_freeze_tier=config.stability_default_freeze_tier,
    )
    return {"status": "ok", "summary": summary, "outputDir": str(output_dir)}


def _handle_validation_biomarker_filter(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    """In-process PPI-only biomarker gene pool filter on mapper combined genes."""
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
    ).model_dump()


def _handle_validation_prepare_freeze(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    from methyl_validation.stability import prepare_freeze_project

    config, base_project = _load_mc_config(input_json)
    mc_root = _resolve_monte_carlo_runs_root(input_json)
    stable_csv = input_json.get("stableDmpCsv") or config.freeze_stable_dmp_csv or str(mc_root / "stability" / "stable_dmps_production.csv")
    result = prepare_freeze_project(
        base_project=base_project,
        stable_dmp_csv=str(stable_csv),
        monte_carlo_runs_root=mc_root,
        production_output_dir=input_json.get("productionOutputDir") or config.production_output_dir,
        config=config,
    )
    return result


def _handle_validation_stability_freeze_readiness(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    from methyl_validation.stability_freeze_readiness import analyze_project_root

    project_path = input_json.get("projectPath") or input_json.get("project")
    if not project_path:
        raise RuntimeError("validation.stability_freeze_readiness requires projectPath")
    from methyl_utils import load_project

    project = load_project(str(project_path))
    project_root = Path(project.output_base) / project.project_name
    report = analyze_project_root(project_root)
    return {"status": "ok", "report": report, "verdict": report.get("verdict", {})}


def _handle_validation_link_artifacts(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    from methyl_validation.project_gen import link_run_artifacts_from_source

    source = input_json.get("sourceRunDir")
    target = input_json.get("targetRunDir") or input_json.get("runDir")
    if not source or not target:
        raise RuntimeError("validation.link_artifacts requires sourceRunDir and targetRunDir")
    linked = link_run_artifacts_from_source(source, target)
    return {"status": "ok", **linked}


def _handle_validation_model_bundle(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    from methyl_validation.model_bundle import build_model_feature_bundle

    project_path = input_json.get("projectPath") or input_json.get("project")
    if not project_path:
        raise RuntimeError("validation.model_bundle requires projectPath")
    bundle_dir = Path(input_json.get("bundleDir") or Path(str(project_path)).parent / "model_bundle")
    manifest = build_model_feature_bundle(str(project_path), bundle_dir)
    return {"status": "ok", "bundleDir": str(bundle_dir), "manifest": str(manifest)}


def _handle_validation_model_train(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
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
    return {"status": "ok", "backend": backend, "summary": summary, "outputDir": str(output_dir)}


def _handle_validation_model_predict(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    backend = str(input_json.get("backend") or "tabular_sklearn")
    project_path = Path(input_json.get("projectPath") or input_json.get("project") or "")
    if not project_path.is_file():
        raise RuntimeError("validation.model_predict requires projectPath")
    run_dir = Path(input_json.get("runDir") or project_path.parent)
    if backend == "tabular_sklearn":
        from methyl_validation.tabular_backend import predict_tabular_model_from_project

        summary = predict_tabular_model_from_project(project_path, output_dir=run_dir)
    elif backend == "generative_hybrid":
        from methyl_validation.generative_backend import predict_generative_model_from_project

        summary = predict_generative_model_from_project(project_path, output_dir=run_dir)
    else:
        raise RuntimeError(
            f"validation.model_predict does not support backend={backend!r}; use pipeline.predictor for ecdf"
        )
    return {"status": "ok", "backend": backend, "summary": summary, "runDir": str(run_dir)}


def _handle_validation_model_mc(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    from methyl_validation.model_mc_runner import run_model_mc_all

    config, _base = _load_mc_config(input_json)
    mc_root = _resolve_monte_carlo_runs_root(input_json)
    production_dir = Path(
        input_json.get("productionOutputDir") or config.production_output_dir or mc_root / "production"
    )
    production_project = production_dir / "project.json"
    backends = input_json.get("backends")
    resume = input_json.get("resume")
    return run_model_mc_all(
        production_project=production_project,
        monte_carlo_runs_root=mc_root,
        config=config,
        backends=list(backends) if backends else None,
        resume=int(resume) if resume is not None else None,
    )


def _handle_validation_select_best_model(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    from methyl_validation.cli import _write_backend_ranking
    from methyl_validation.stability import build_production_model

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
    import json

    selection_payload = {
        "selected_backend": best_backend,
        "selection_metric": metric,
        "selection_stat": stat,
        "ranking": ranking,
    }
    selection_path.write_text(json.dumps(selection_payload, indent=2) + "\n", encoding="utf-8")
    return {
        "status": "ok",
        "selectedBackend": best_backend,
        "ranking": ranking,
        "productionSummary": summary,
        "selectionPath": str(selection_path),
    }


def _handle_validation_post_model_validation(
    _capability: str, _action_name: str, input_json: Dict[str, Any]
) -> HandlerResult:
    from methyl_validation.pipeline_runner import (
        run_post_model_validation_binary,
        run_post_model_validation_multiclass,
    )
    from methyl_validation.project_gen import infer_monte_carlo_layout

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
    return {
        "status": "ok" if success else "failed",
        "success": success,
        "errors": errors,
        "timings": timings,
        "runDir": str(run_dir),
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
                "qcMetricsTar": (
                    f"{sample_dir}/{sample_id}.qc-metrics.tar" if sample_dir else f"{sample_id}.qc-metrics.tar"
                ),
            }
        if capability == "sample.delete-fastqs":
            return {"sampleId": sample_id, "deleted": True}
        if capability == "sample.trim-fastq":
            return {
                "sampleId": sample_id,
                "trimFront2": str(input_json.get("trimFront2", 5)),
                "trimmedR1": f"{sample_dir}/{sample_id}_1.trimmed.fastq.gz",
                "trimmedR2": f"{sample_dir}/{sample_id}_2.trimmed.fastq.gz",
            }
        if capability == "sample.delete-bam":
            return {"sampleId": sample_id, "deleted": True}
        if capability == "methyl-extract":
            return {"sampleId": sample_id, "h5Files": ["1-CG.h5"]}
        if capability == "sample.upload-h5":
            return {
                "sampleId": sample_id,
                "uploadedFiles": ["1-CG.h5"],
                "skippedFiles": [],
                "remotePrefix": "studies/test/",
                "uploadedCount": 1,
                "skippedCount": 0,
            }
    raise RuntimeError(
        f"No local handler for capability {capability!r}. "
        "Implement a domain worker or set WORKER_STUB_EXTERNAL=1 for dry-run."
    )


_SAMPLE_PREP_DOMAIN_ACTIONS = frozenset({
    "sample.download_fastq",
    "sample.parabricks_fq2bam",
    "sample.trim_fastq",
    "sample.methyl_qc",
    "sample.fragmentomics",
    "sample.methyl_extract",
    "sample.extraction_qc",
    "sample.upload_h5",
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
