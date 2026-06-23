"""
Build SamplePrepPipeline context_json from project + sample lists + structured FASTQ storage.

Used by:
- middle-tier REST ``POST /v1/studies/sample-prep/start``
- ``methyl-validation plan-sample-prep-context`` CLI (optional)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from methyl_domain.fastq_storage import (
    FastqSourceLocation,
    FastqStorageDefaults,
    merge_fastq_source,
    normalize_sample_prefix,
)
from methyl_domain.h5_storage import (
    H5DestinationLocation,
    H5StorageDefaults,
    merge_h5_destination,
)
from pydantic import BaseModel, Field, TypeAdapter

from .cohort_inference import infer_monte_carlo_cohorts_from_project
from .workflow_planner import resolve_base_project_json

__all__ = [
    "SamplePrepPlanRequest",
    "plan_sample_prep_context",
]

_CLOUD_SCHEMES = ("s3://", "az://", "file://")
_FASTQ_SOURCE_ADAPTER = TypeAdapter(FastqSourceLocation)
_H5_DEST_ADAPTER = TypeAdapter(H5DestinationLocation)


class SamplePrepPlanRequest(BaseModel):
    """Input for sample prep instance planning."""

    projectPath: str = Field(..., description="Path to base project.json or project directory")
    samples: Optional[List[Dict[str, Any]]] = None
    sampleCsv: Optional[str] = None
    sampleCsvs: Optional[List[str]] = None
    useProjectSamples: bool = False
    fastqStorage: FastqStorageDefaults
    h5Storage: Optional[H5StorageDefaults] = None
    samplesBaseDir: Optional[str] = None
    referenceFasta: Optional[str] = None
    referenceGtf: Optional[str] = None
    primaryAnalyte: Optional[str] = None


def _is_legacy_uri(entry: str) -> bool:
    e = entry.strip().lower()
    return any(e.startswith(scheme) for scheme in _CLOUD_SCHEMES)


def _sample_id_from_resolved_path(path: str) -> str:
    return Path(str(path).rstrip("/")).name


def _default_prefix(sample_id: str) -> str:
    return normalize_sample_prefix(sample_id)


def _materialize_fastq_source(
    storage: FastqStorageDefaults,
    *,
    sample_id: str,
    fastq_prefix: Optional[str] = None,
    fastq_source_override: Any = None,
) -> tuple[str, Dict[str, Any]]:
    if fastq_source_override is not None:
        source = _FASTQ_SOURCE_ADAPTER.validate_python(fastq_source_override)
        prefix = normalize_sample_prefix(source.prefix or fastq_prefix or sample_id)
        return prefix, source.model_dump(mode="json")
    prefix = normalize_sample_prefix(fastq_prefix or sample_id)
    source = merge_fastq_source(storage, prefix)
    return prefix, source.model_dump(mode="json")


def _materialize_h5_destination(
    storage: H5StorageDefaults,
    *,
    sample_id: str,
    h5_prefix: Optional[str] = None,
    h5_destination_override: Any = None,
) -> tuple[str, Dict[str, Any]]:
    if h5_destination_override is not None:
        dest = _H5_DEST_ADAPTER.validate_python(h5_destination_override)
        prefix = normalize_sample_prefix(dest.prefix or h5_prefix or sample_id)
        return prefix, dest.model_dump(mode="json")
    prefix = normalize_sample_prefix(h5_prefix or sample_id)
    dest = merge_h5_destination(storage, prefix)
    return prefix, dest.model_dump(mode="json")


def _sample_entry(
    *,
    sample_id: str,
    sample_dir: str,
    storage: FastqStorageDefaults,
    fastq_prefix: Optional[str] = None,
    fastq_source_override: Any = None,
    trim_front2: Optional[int] = None,
    h5_storage: Optional[H5StorageDefaults] = None,
    h5_prefix: Optional[str] = None,
    h5_destination_override: Any = None,
) -> Dict[str, Any]:
    prefix, fastq_source = _materialize_fastq_source(
        storage,
        sample_id=sample_id,
        fastq_prefix=fastq_prefix,
        fastq_source_override=fastq_source_override,
    )
    entry: Dict[str, Any] = {
        "sampleId": sample_id,
        "sampleDir": sample_dir,
        "fastqPrefix": prefix,
        "fastqSource": fastq_source,
    }
    if trim_front2 is not None:
        entry["trimFront2"] = trim_front2
    if h5_storage is not None:
        h5_pfx, h5_dest = _materialize_h5_destination(
            h5_storage,
            sample_id=sample_id,
            h5_prefix=h5_prefix,
            h5_destination_override=h5_destination_override,
        )
        entry["h5Prefix"] = h5_pfx
        entry["h5Destination"] = h5_dest
    return entry


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
    storage: FastqStorageDefaults,
    h5_storage: Optional[H5StorageDefaults] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    base = Path(samples_base).resolve()
    for csv_path in csv_paths:
        for raw_entry in _load_raw_csv_entries(csv_path):
            if _is_legacy_uri(raw_entry):
                raise ValueError(
                    f"legacy FASTQ URI in CSV is not supported ({raw_entry!r}); "
                    "use fastqStorage + per-sample fastqPrefix"
                )
            if _looks_like_absolute_path(raw_entry):
                sample_id = _sample_id_from_resolved_path(raw_entry)
            else:
                sample_id = raw_entry.strip()
            if not sample_id:
                continue
            out.append(
                _sample_entry(
                    sample_id=sample_id,
                    sample_dir=str(base / sample_id),
                    storage=storage,
                    fastq_prefix=_default_prefix(sample_id),
                    h5_storage=h5_storage,
                )
            )
    return out


def _looks_like_absolute_path(entry: str) -> bool:
    e = entry.strip()
    return e.startswith("/") or (len(e) > 1 and e[1] == ":")


def _merge_explicit_samples(
    explicit: List[Dict[str, Any]],
    samples_base: str,
    *,
    storage: FastqStorageDefaults,
    h5_storage: Optional[H5StorageDefaults] = None,
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
        if item.get("fastqSourceUri") or item.get("fastqUri"):
            raise ValueError(
                f"legacy fastqSourceUri/fastqUri on sample {sample_id!r} is not supported; "
                "use fastqPrefix or fastqSource"
            )
        sample_dir = item.get("sampleDir") or str(base / sample_id)
        trim_front2 = item.get("trimFront2")
        out.append(
            _sample_entry(
                sample_id=sample_id,
                sample_dir=str(Path(str(sample_dir)).resolve()),
                storage=storage,
                fastq_prefix=item.get("fastqPrefix"),
                fastq_source_override=item.get("fastqSource"),
                trim_front2=int(trim_front2) if trim_front2 is not None else None,
                h5_storage=h5_storage,
                h5_prefix=item.get("h5Prefix"),
                h5_destination_override=item.get("h5Destination"),
            )
        )
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

    storage = request.fastqStorage
    h5_storage = request.h5Storage

    merged: List[Dict[str, Any]] = []
    if request.samples:
        merged.extend(
            _merge_explicit_samples(
                list(request.samples),
                samples_base,
                storage=storage,
                h5_storage=h5_storage,
            )
        )

    csv_paths = _collect_csv_paths(payload, project_data, base_project)
    if csv_paths:
        merged.extend(
            _load_samples_from_csvs(
                csv_paths,
                samples_base,
                storage=storage,
                h5_storage=h5_storage,
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
        "fastqStorage": storage.model_dump(mode="json"),
        "samples": samples,
    }
    if h5_storage is not None:
        context["h5Storage"] = h5_storage.model_dump(mode="json")

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
