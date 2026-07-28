"""Sample-prep and alignment in-process handlers."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel

from ..handler_helpers import (
    guardrails_from_payload,
    methyl_qc_result_code,
    qc_history_from_payload,
    screening_from_payload,
)
from ..task_models.sample_prep_models import MethylQcTaskOutput
from .common import resolve_reference_fasta

logger = logging.getLogger(__name__)

def _handle_methyl_qc(_capability: str, _action_name: str, input: BaseModel) -> MethylQcTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir:
        raise RuntimeError("methyl-qc task requires sampleDir in input_json")

    sample_path = Path(str(sample_dir))
    if not sample_path.is_dir():
        raise RuntimeError(f"sampleDir not found: {sample_path}")

    from methyl_alignment_qc.core import resolve_sample_artifact_id

    # sampleDir may be an experiment mode leaf (.../<sampleId>/linear); artifacts
    # remain named {sampleId}.bam — never use sample_path.name as the sample id.
    resolved_sample_id = resolve_sample_artifact_id(
        sample_path, str(sample_id) if sample_id else None
    )

    project = input_json.get("project") or input_json.get("projectPath")
    from methyl_alignment_qc.core import process_samples_to_qc_jsons
    from methyl_alignment_qc.core.qc_write_context import QcWriteContext

    write_ctx = QcWriteContext.from_input_json(input_json)
    write_ctx.sample_prep_log_path = str(
        sample_path / f"{resolved_sample_id}.sample_prep_log.jsonl"
    )

    def _build_result(qc_path: Path) -> MethylQcTaskOutput:
        from ..sample_prep_log import append_sample_prep_log

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
            sample_id=resolved_sample_id,
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
            sampleId=resolved_sample_id,
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
        qc_path = Path(out_dir) / f"{resolved_sample_id}.json"
        if qc_path.is_file():
            # Use module-level json (do not re-import here — that makes `json` a
            # function-local name and breaks _build_result when this branch is skipped).
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
            sample_id=resolved_sample_id,
        )
        qc_path = Path(out_dir) / f"{resolved_sample_id}.json"
    else:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="methyl-qc-") as tmp:
            out_dir = tmp
            process_samples_to_qc_jsons(
                [str(sample_path)],
                out_dir,
                write_context=write_ctx,
                sample_id=resolved_sample_id,
            )
            qc_path = Path(out_dir) / f"{resolved_sample_id}.json"
            return _build_result(qc_path)

    if not qc_path.is_file():
        raise RuntimeError(f"QC JSON not written: {qc_path}")

    return _build_result(qc_path)


def _handle_methyl_extraction_qc(
    _capability: str, _action_name: str, input: BaseModel
) -> "ExtractionQcTaskOutput":
    from ..task_models.sample_prep_models import ExtractionQcTaskOutput

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

    from ..sample_prep_log import append_sample_prep_log

    from ..handler_helpers import guardrails_from_payload

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
    from ..task_models.sample_prep_models import FragmentomicsTaskOutput

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


def _handle_mark_failed(_capability: str, _action_name: str, input: BaseModel):
    from ..task_models.sample_prep_models import MarkFailedTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")

    return MarkFailedTaskOutput(
        sampleId=input_json.get("sampleId"),
        sampleDir=input_json.get("sampleDir"),
        status="QC_FAILED",
        reason=input_json.get("reason") or "alignment_qc_failed",
    )


def _handle_download_fastq(_capability: str, _action_name: str, input: BaseModel) -> DownloadFastqTaskOutput:
    from ..fastq_source import download_from_source
    from ..task_models import DownloadFastqTaskInput, DownloadFastqTaskOutput

    task = input if isinstance(input, DownloadFastqTaskInput) else DownloadFastqTaskInput.model_validate(
        input.model_dump(mode="json")
    )
    dest = Path(str(task.sampleDir))
    fastq_files = download_from_source(
        task.fastqSource, dest, resolved_config=task.resolvedConfig
    )
    sample_id = task.sampleId or dest.name
    return DownloadFastqTaskOutput(
        status="ok",
        sampleId=sample_id,
        fastqFiles=fastq_files,
        n_files=len(fastq_files),
    )


def _handle_trim_fastq(_capability: str, _action_name: str, input: BaseModel) -> TrimFastqTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from ..fastq_trim_runner import run_fastp_trim
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.sample_prep_models import TrimFastqTaskOutput

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
    from ..parabricks_runner import run_fq2bam_meth
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.sample_prep_models import ParabricksTaskOutput

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.parabricks_fq2bam requires sampleDir and sampleId")
    reference_fasta = resolve_reference_fasta(input_json)

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


def _handle_parabricks_giraffe(_capability: str, _action_name: str, input: BaseModel) -> ParabricksTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from ..giraffe_runner import run_giraffe_align
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.sample_prep_models import ParabricksTaskOutput

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.parabricks_giraffe requires sampleDir and sampleId")

    site_path = input_json.get("siteConfigPath")
    result = run_giraffe_align(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        project=input_json.get("projectPath") or input_json.get("project"),
        input_json=input_json,
        site_path=str(site_path) if site_path else None,
    )
    reason = str(input_json.get("remediationReason") or "")
    if input_json.get("forceRealign"):
        reason = reason or f"forceRealign after trim_front2={input_json.get('trimFront2', '?')}"
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.parabricks_giraffe",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason=reason or "Parabricks giraffe pangenome alignment",
        inputs={
            "forceRealign": bool(input_json.get("forceRealign")),
            "alignmentPass": input_json.get("alignmentPass") or "initial",
            "alignmentMode": "pangenome",
        },
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "parabricks_giraffe",
    )
    return ParabricksTaskOutput(status="ok", **result)


def _handle_methylgrapher_wgbs_align(
    _capability: str, _action_name: str, input: BaseModel
) -> "MethylGrapherWgbsAlignTaskOutput":
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from ..methylgrapher_wgbs_runner import run_methylgrapher_wgbs_align
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.sample_prep_models import MethylGrapherWgbsAlignTaskOutput

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.methylgrapher_wgbs_align requires sampleDir and sampleId")
    result = run_methylgrapher_wgbs_align(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        input_json=input_json,
    )
    reason = str(input_json.get("remediationReason") or "")
    if input_json.get("forceRealign"):
        reason = reason or f"forceRealign after trim_front2={input_json.get('trimFront2', '?')}"
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.methylgrapher_wgbs_align",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason=reason or "methylGrapher C2T/G2A WGBS pangenome alignment",
        inputs={
            "forceRealign": bool(input_json.get("forceRealign")),
            "alignmentPass": input_json.get("alignmentPass") or "initial",
            "alignmentMode": "pangenome_wgbs",
        },
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "methylgrapher_wgbs_align",
    )
    return MethylGrapherWgbsAlignTaskOutput(status="ok", **result)


def _handle_methylgrapher_wgbs_extract(_capability: str, _action_name: str, input: BaseModel):
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from ..methylgrapher_wgbs_runner import run_methylgrapher_wgbs_extract
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.sample_prep_models import MethylExtractTaskOutput

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    project = input_json.get("project") or input_json.get("projectPath")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.methylgrapher_wgbs_extract requires sampleDir and sampleId")
    if not project:
        raise RuntimeError("sample.methylgrapher_wgbs_extract requires projectPath")
    raw = run_methylgrapher_wgbs_extract(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        project=str(project),
        input_json=input_json,
    )
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.methylgrapher_wgbs_extract",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason="methylGrapher graph-aware methylation extraction",
        inputs={"forceRealign": bool(input_json.get("forceRealign"))},
        outputs=raw,
        workflow_node_key=input_json.get("workflowNodeKey") or "methylgrapher_wgbs_extract",
    )
    h5_files = list(raw.get("h5Files") or [])
    return MethylExtractTaskOutput(
        status="ok",
        sampleId=str(raw.get("sampleId") or sample_id),
        h5Files=h5_files,
        n_h5_files=len(h5_files),
    )


def _handle_delete_fastqs(_capability: str, _action_name: str, input: BaseModel) -> DeleteTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from ..task_models.sample_prep_models import DeleteTaskOutput

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
    from ..task_models.sample_prep_models import DeleteTaskOutput

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
    from ..extract_runner import run_methyl_extract
    from ..task_models.sample_prep_models import MethylExtractTaskOutput

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
    from ..sample_archive import archive_from_task_input
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.sample_prep_models import ArchiveSampleTaskOutput

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
            reason=str(
                input_json.get("rejectReason")
                or result.get("skipReason")
                or "Archive sample bundle to durable storage"
            ),
            inputs={"mode": result.get("archiveMode"), "remotePrefix": result.get("remotePrefix")},
            outputs=result,
            workflow_node_key=input_json.get("workflowNodeKey") or "archive_sample",
        )
    status = "skipped" if result.get("archiveSkipped") else "ok"
    return ArchiveSampleTaskOutput(status=status, **result)


def _handle_demultiplex(_capability: str, _action_name: str, input: BaseModel) -> "DemultiplexTaskOutput":
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from ..demultiplex_runner import run_demultiplex
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.sample_prep_models import DemultiplexTaskOutput

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.demultiplex requires sampleDir and sampleId")
    resolved = dict(input_json.get("resolvedConfig") or {})
    if input_json.get("barcodeTsv") and not resolved.get("barcode_tsv"):
        resolved["barcode_tsv"] = input_json["barcodeTsv"]
    payload = {**input_json, "resolvedConfig": resolved}
    result = run_demultiplex(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        input_json=payload,
    )
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.demultiplex",
        capability=_capability,
        attempt=1,
        reason="Barcode demultiplex (epi-GBS / reduced-rep)",
        inputs={"barcodeTsv": resolved.get("barcode_tsv"), "skipped": result.get("skipped")},
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "demultiplex",
    )
    status = "skipped" if result.get("skipped") else "ok"
    return DemultiplexTaskOutput(status=status, **result)


def _handle_docker_align(_capability: str, _action_name: str, input: BaseModel) -> ParabricksTaskOutput:
    input_json: Dict[str, Any] = input.model_dump(mode="json")
    from ..docker_align_runner import run_docker_align
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.sample_prep_models import ParabricksTaskOutput

    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.docker_align requires sampleDir and sampleId")
    reference_fasta = resolve_reference_fasta(input_json)
    result = run_docker_align(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        reference_fasta=reference_fasta,
        input_json=input_json,
    )
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.docker_align",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason=str(input_json.get("remediationReason") or "Generic Docker methylation align"),
        inputs={
            "forceRealign": bool(input_json.get("forceRealign")),
            "alignmentPass": input_json.get("alignmentPass") or "initial",
        },
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "docker_align",
    )
    return ParabricksTaskOutput(status="ok", **result)



