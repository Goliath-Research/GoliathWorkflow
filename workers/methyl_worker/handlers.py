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


def _handle_download_fastq(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    from .fastq_source import download_fastqs

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    source_uri = input_json.get("fastqSourceUri") or input_json.get("fastqUri")
    if not sample_dir:
        raise RuntimeError("sample.download_fastq requires sampleDir")
    if not source_uri:
        raise RuntimeError("sample.download_fastq requires fastqSourceUri")

    dest = Path(str(sample_dir))
    fastq_files = download_fastqs(str(source_uri), dest)
    return {"sampleId": sample_id or dest.name, "fastqFiles": fastq_files}


def _handle_parabricks_fq2bam(_capability: str, _action_name: str, input_json: Dict[str, Any]) -> HandlerResult:
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    reference_fasta = input_json.get("referenceFasta")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.parabricks_fq2bam requires sampleDir and sampleId")
    if not reference_fasta:
        raise RuntimeError("sample.parabricks_fq2bam requires referenceFasta")

    sample_path = Path(str(sample_dir))
    bam_path = sample_path / f"{sample_id}.bam"
    metrics_json = sample_path / f"{sample_id}.json"
    if bam_path.is_file() and metrics_json.is_file():
        return {
            "sampleId": sample_id,
            "bamPath": str(bam_path),
            "metricsJson": str(metrics_json),
        }

    fastqs = sorted(
        list(sample_path.glob("*.fastq.gz"))
        + list(sample_path.glob("*.fq.gz"))
        + list(sample_path.glob("*.fastq"))
        + list(sample_path.glob("*.fq"))
    )
    if not fastqs:
        raise RuntimeError(f"No FASTQ files under {sample_path}")

    pbrun = shutil.which("pbrun")
    if pbrun is None:
        raise RuntimeError("pbrun not found on PATH; install Parabricks or set WORKER_STUB_EXTERNAL=1")

    cmd = [
        pbrun,
        "fq2bam",
        f"--ref={reference_fasta}",
        f"--in-fq={','.join(str(p) for p in fastqs)}",
        f"--out-bam={bam_path}",
        f"--out-json={metrics_json}",
    ]
    gtf = input_json.get("referenceGtf")
    if gtf:
        cmd.append(f"--ref-gtf={gtf}")
    logger.info("Running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "pbrun fq2bam failed")
    return {
        "sampleId": sample_id,
        "bamPath": str(bam_path),
        "metricsJson": str(metrics_json),
    }


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
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    project = input_json.get("project") or input_json.get("projectPath")
    reference_fasta = input_json.get("referenceFasta")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.methyl_extract requires sampleDir and sampleId")
    if not project:
        raise RuntimeError("sample.methyl_extract requires project")

    sample_path = Path(str(sample_dir))
    from methyl_utils import load_project

    project_obj = load_project(str(project))
    chromosomes = list(project_obj.chromosomes or [])
    contexts = list(getattr(project_obj, "contexts", None) or ["CG"])
    expected = [f"{chrom}-{ctx}.h5" for chrom in chromosomes for ctx in contexts]
    existing = [name for name in expected if (sample_path / name).is_file()]
    if len(existing) == len(expected) and expected:
        return {"sampleId": sample_id, "h5Files": existing}

    bam_candidates = [
        sample_path / f"{sample_id}.bam",
        sample_path / f"{sample_id}.BAM",
    ]
    bam_path = next((p for p in bam_candidates if p.is_file()), None)
    if bam_path is None:
        raise RuntimeError(f"BAM not found for methyl extract under {sample_path}")

    extract_cli = shutil.which("methyl-extract")
    if extract_cli is None:
        raise RuntimeError(
            "methyl-extract not found on PATH; install MethylExtractor or set WORKER_STUB_EXTERNAL=1"
        )

    if reference_fasta is None:
        alignment_cfg = (project_obj.get_step_config("alignment_qc") or {}) if hasattr(project_obj, "get_step_config") else {}
        reference_fasta = alignment_cfg.get("genome_fasta")

    cmd = [extract_cli, "--project", str(project), "--sample-dir", str(sample_path)]
    if reference_fasta:
        cmd.extend(["--reference-fasta", str(reference_fasta)])
    logger.info("Running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "methyl-extract failed")

    h5_files = [name for name in expected if (sample_path / name).is_file()]
    if not h5_files:
        h5_files = [p.name for p in sorted(sample_path.glob("*-*.h5"))]
    return {"sampleId": sample_id, "h5Files": h5_files}


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
