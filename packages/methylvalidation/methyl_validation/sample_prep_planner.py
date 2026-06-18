"""
Build SamplePrepPipeline context_json from project + sample lists + cloud FASTQ URIs.

Used by:
- middle-tier REST ``POST /v1/studies/sample-prep/start``
- ``methyl-validation plan-sample-prep-context`` CLI (optional)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from .cohort_inference import infer_monte_carlo_cohorts_from_project
from .workflow_planner import resolve_base_project_json

__all__ = [
    "SamplePrepPlanRequest",
    "plan_sample_prep_context",
]

_CLOUD_SCHEMES = ("s3://", "az://", "file://")


class SamplePrepPlanRequest(BaseModel):
    """Input for sample prep instance planning."""

    projectPath: str = Field(..., description="Path to base project.json or project directory")
    samples: Optional[List[Dict[str, Any]]] = None
    sampleCsv: Optional[str] = None
    sampleCsvs: Optional[List[str]] = None
    useProjectSamples: bool = False
    fastqBaseUri: Optional[str] = None
    fastqUriTemplate: Optional[str] = None
    samplesBaseDir: Optional[str] = None
    referenceFasta: Optional[str] = None
    referenceGtf: Optional[str] = None
    primaryAnalyte: Optional[str] = None


def _is_cloud_or_file_uri(entry: str) -> bool:
    e = entry.strip().lower()
    return any(e.startswith(scheme) for scheme in _CLOUD_SCHEMES)


def _sample_id_from_resolved_path(path: str) -> str:
    return Path(str(path).rstrip("/")).name


def _normalize_uri_prefix(prefix: str) -> str:
    p = str(prefix).strip()
    if not p:
        return p
    if not p.endswith("/"):
        p += "/"
    return p


def _build_fastq_uri(
    sample_id: str,
    *,
    resolved_path: Optional[str],
    fastq_base_uri: Optional[str],
    fastq_uri_template: Optional[str],
) -> str:
    if resolved_path and _is_cloud_or_file_uri(resolved_path):
        return resolved_path.rstrip("/") + ("/" if resolved_path.endswith("/") else "")
    if not fastq_base_uri and not fastq_uri_template:
        raise ValueError(
            f"fastqBaseUri or fastqUriTemplate required for sample {sample_id!r} "
            f"(resolved path is not s3://, az://, or file://)"
        )
    template = fastq_uri_template or f"{{fastqBaseUri}}{{sampleId}}/"
    base = _normalize_uri_prefix(fastq_base_uri or "")
    uri = template.format(fastqBaseUri=base, sampleId=sample_id)
    if not uri.endswith("/"):
        uri += "/"
    return uri


def _collect_csv_paths(body: Dict[str, Any], project_data: Dict[str, Any], project_path: Path) -> List[str]:
    csvs: List[str] = []
    if body.get("sampleCsv"):
        csvs.append(str(body["sampleCsv"]))
    for item in body.get("sampleCsvs") or []:
        csvs.append(str(item))
    if body.get("useProjectSamples"):
        for cohort in infer_monte_carlo_cohorts_from_project(project_data, project_path):
            csvs.append(str(cohort["csv"]))
    return csvs


def _load_raw_csv_entries(csv_path: str | Path) -> List[str]:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Sample list file not found: {path}")
    out: List[str] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        first_row = next(reader, None)
        if first_row is None:
            return out
        header = first_row[0].strip().lower() if first_row else ""
        if header in ("sample", "path", "sample_path", "name", "id"):
            for row in reader:
                if row and row[0].strip():
                    out.append(row[0].strip())
        else:
            if first_row and first_row[0].strip():
                out.append(first_row[0].strip())
            for row in reader:
                if row and row[0].strip():
                    out.append(row[0].strip())
    return out


def _load_samples_from_csvs(
    csv_paths: List[str],
    samples_base: str,
    *,
    fastq_base_uri: Optional[str],
    fastq_uri_template: Optional[str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    base = Path(samples_base).resolve()
    for csv_path in csv_paths:
        for raw_entry in _load_raw_csv_entries(csv_path):
            if _is_cloud_or_file_uri(raw_entry):
                sample_id = _sample_id_from_resolved_path(raw_entry.rstrip("/"))
                fastq_uri = raw_entry if raw_entry.endswith("/") else raw_entry + "/"
                out.append(
                    {
                        "sampleId": sample_id,
                        "sampleDir": str(base / sample_id),
                        "fastqSourceUri": fastq_uri,
                    }
                )
                continue
            resolved = raw_entry
            if not _looks_like_absolute_path(resolved):
                resolved = str(base / resolved)
            sample_id = _sample_id_from_resolved_path(resolved)
            fastq_uri = _build_fastq_uri(
                sample_id,
                resolved_path=resolved,
                fastq_base_uri=fastq_base_uri,
                fastq_uri_template=fastq_uri_template,
            )
            out.append(
                {
                    "sampleId": sample_id,
                    "sampleDir": str(base / sample_id),
                    "fastqSourceUri": fastq_uri,
                }
            )
    return out


def _looks_like_absolute_path(entry: str) -> bool:
    e = entry.strip()
    return e.startswith("/") or (len(e) > 1 and e[1] == ":")


def _merge_explicit_samples(
    explicit: List[Dict[str, Any]],
    samples_base: str,
    *,
    fastq_base_uri: Optional[str],
    fastq_uri_template: Optional[str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    base = Path(samples_base).resolve()
    for item in explicit:
        if not isinstance(item, dict):
            continue
        sample_id = str(item.get("sampleId") or "").strip()
        if not sample_id:
            raw_path = item.get("sampleDir") or item.get("path")
            if raw_path:
                sample_id = _sample_id_from_resolved_path(str(raw_path))
        if not sample_id:
            raise ValueError("each explicit sample requires sampleId or sampleDir")
        sample_dir = item.get("sampleDir") or str(base / sample_id)
        fastq_uri = item.get("fastqSourceUri") or item.get("fastqUri")
        if not fastq_uri:
            fastq_uri = _build_fastq_uri(
                sample_id,
                resolved_path=item.get("fastqSourceUri") or item.get("path"),
                fastq_base_uri=fastq_base_uri,
                fastq_uri_template=fastq_uri_template,
            )
        entry: Dict[str, Any] = {
            "sampleId": sample_id,
            "sampleDir": str(Path(str(sample_dir)).resolve()),
            "fastqSourceUri": fastq_uri,
        }
        if item.get("trimFront2") is not None:
            entry["trimFront2"] = int(item["trimFront2"])
        out.append(entry)
    return out


def _dedupe_samples(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for item in samples:
        sid = str(item["sampleId"])
        if sid in seen:
            continue
        seen.add(sid)
        out.append(item)
    return out


def _default_reference_fasta(project) -> Optional[str]:
    aq = project.get_step_config("alignment_qc") or {}
    for key in ("genome_fasta", "reference_fasta", "referenceFasta"):
        val = aq.get(key)
        if val:
            return str(val)
    return None


def _default_reference_gtf(project) -> Optional[str]:
    aq = project.get_step_config("alignment_qc") or {}
    for key in ("reference_gtf", "referenceGtf", "gtf"):
        val = aq.get(key)
        if val:
            return str(val)
    return None


def plan_sample_prep_context(body: Dict[str, Any] | SamplePrepPlanRequest) -> Dict[str, Any]:
    """
    Build SamplePrepPipeline ``context_json`` from project + sample list sources.

    Merges explicit ``samples[]``, ``sampleCsv`` / ``sampleCsvs``, and optional
    ``useProjectSamples`` (union of project cohort CSVs). Dedupes by ``sampleId``.
    """
    request = (
        body
        if isinstance(body, SamplePrepPlanRequest)
        else SamplePrepPlanRequest.model_validate(body)
    )
    payload = request.model_dump(exclude_none=True)

    base_project = resolve_base_project_json(request.projectPath)
    with open(base_project, encoding="utf-8") as f:
        project_data = json.load(f)

    from methyl_utils import load_project

    project = load_project(str(base_project))

    samples_base = request.samplesBaseDir or project_data.get("samples_base_path") or "/work/samples"
    samples_base = str(Path(str(samples_base)).expanduser().resolve())

    fastq_base = request.fastqBaseUri
    fastq_template = request.fastqUriTemplate

    merged: List[Dict[str, Any]] = []
    if request.samples:
        merged.extend(
            _merge_explicit_samples(
                list(request.samples),
                samples_base,
                fastq_base_uri=fastq_base,
                fastq_uri_template=fastq_template,
            )
        )

    csv_paths = _collect_csv_paths(payload, project_data, base_project)
    if csv_paths:
        merged.extend(
            _load_samples_from_csvs(
                csv_paths,
                samples_base,
                fastq_base_uri=fastq_base,
                fastq_uri_template=fastq_template,
            )
        )

    samples = _dedupe_samples(merged)
    if not samples:
        raise ValueError(
            "No samples resolved; provide samples[], sampleCsv/sampleCsvs, or useProjectSamples=true"
        )

    primary = request.primaryAnalyte or project.get_primary_analyte() or "buffy_coat"
    is_cfdna = str(primary).lower() in {"cfdna", "plasma_cfdna", "cf_dna"}

    context: Dict[str, Any] = {
        "projectPath": str(base_project.resolve()),
        "primaryAnalyte": primary,
        "isCfdna": is_cfdna,
        "samples": samples,
    }

    ref_fasta = request.referenceFasta or _default_reference_fasta(project)
    if ref_fasta:
        context["referenceFasta"] = str(ref_fasta)
    else:
        raise ValueError(
            "referenceFasta is required; set referenceFasta in request or step_config.alignment_qc.genome_fasta"
        )

    ref_gtf = request.referenceGtf or _default_reference_gtf(project)
    if ref_gtf is not None:
        context["referenceGtf"] = str(ref_gtf)

    return context
