"""Pydantic models for workflow ACTION input_json / output_json payloads."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from methyl_domain.fastq_storage import FastqSourceLocation
from methyl_domain.sample_storage import SampleDestinationLocation
from methyl_domain.h5_storage import H5DestinationLocation  # deprecated alias
from pydantic import BaseModel, ConfigDict, Field


class PipelineCliTaskInput(BaseModel):
    """Shared input for methyl-* pipeline CLI actions (centroid, detector, mapper, enricher, progression)."""

    model_config = ConfigDict(extra="allow")

    tool: str
    project: Optional[str] = None
    projectPath: Optional[str] = None
    project_path: Optional[str] = None
    phase: Optional[str] = None
    runId: Optional[str] = None
    taskConfig: Optional[Dict[str, Any]] = None
    group: Optional[str] = None
    chromosome: Optional[str] = None
    context: Optional[str] = None
    comparison: Optional[str] = None
    outputDir: Optional[str] = None
    centroid1Dir: Optional[str] = None
    centroid2Dir: Optional[str] = None
    orderedComparisonLabels: Optional[List[str]] = None
    stepOverride: Optional[Dict[str, Any]] = None
    addSamples: Optional[List[str]] = None
    removeSamples: Optional[List[str]] = None
    fixedDmpPanel: Optional[str] = None


class PipelineCliTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = "ok"
    tool: Optional[str] = None
    stdout_tail: Optional[str] = None


class SamplePrepTaskInput(BaseModel):
    """Shared base for per-sample upstream preprocessing task input."""

    model_config = ConfigDict(extra="allow")

    sampleId: Optional[str] = None
    sampleDir: Optional[str] = None
    project: Optional[str] = None
    projectPath: Optional[str] = None
    reason: Optional[str] = None
    fastqUri: Optional[str] = None


class DownloadFastqTaskInput(BaseModel):
    """Input for sample.download_fastq (SampleDownloadFastq)."""

    model_config = ConfigDict(extra="forbid")

    tool: str = "SampleDownloadFastq"
    sampleId: str
    sampleDir: str
    fastqSource: FastqSourceLocation


class ParabricksFq2bamTaskInput(BaseModel):
    """Input for sample.parabricks_fq2bam (Parabricks fq2bam_meth via Docker)."""

    model_config = ConfigDict(extra="allow")

    tool: str = "ParabricksFq2Bam"
    sampleId: str
    sampleDir: str
    referenceFasta: str
    referenceGtf: Optional[str] = None
    parabricksImage: Optional[str] = None
    bwaThreads: Optional[int] = None


class MethylExtractTaskInput(BaseModel):
    """Input for sample.methyl_extract (MethylExtractor → {chr}-{ctx}.h5 per chromosome)."""

    model_config = ConfigDict(extra="allow")

    tool: str = "MethylExtract"
    sampleId: str
    sampleDir: str
    project: Optional[str] = None
    projectPath: Optional[str] = None
    referenceFasta: Optional[str] = None
    extractContexts: Optional[List[Literal["CG", "CHG", "CHH"]]] = None
    threads: Optional[int] = None
    minMapq: Optional[int] = None
    minPhred: Optional[int] = None
    minCov: Optional[int] = None
    capCov: Optional[int] = None
    chromMapping: Optional[str] = None
    compression: Optional[int] = None
    chunkSize: Optional[int] = None
    outputFormat: Optional[str] = None
    split: Optional[bool] = None
    extractorBin: Optional[str] = None


class SampleIdOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: Optional[str] = None


class MethylQcTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: str
    qcPath: str
    guardrails: Dict[str, Any] = Field(default_factory=dict)
    screening: Dict[str, Any] = Field(default_factory=dict)
    qcHistory: List[Dict[str, Any]] = Field(default_factory=list)
    remediateAlignment: bool = False
    remediateR2Trim: bool = False


class TrimFastqTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: str
    trimFront1: str = "0"
    trimTail1: str = "0"
    trimFront2: str = "0"
    trimTail2: str = "0"
    trimmedR1: str
    trimmedR2: str
    logReason: str = ""


class FragmentomicsTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: str
    outputDir: str
    summary: Dict[str, Any] = Field(default_factory=dict)


class MarkFailedTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: Optional[str] = None
    sampleDir: Optional[str] = None
    status: str = "QC_FAILED"
    reason: str = "alignment_qc_failed"


class DownloadFastqTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: Optional[str] = None
    fastqFiles: List[str] = Field(default_factory=list)


class ParabricksTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: Optional[str] = None
    bamPath: Optional[str] = None
    metricsJson: Optional[str] = None
    qcMetricsTar: Optional[str] = None


class DeleteTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: Optional[str] = None
    deleted: bool = True


class ExtractionQcTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: str
    qcPath: str
    guardrails: Dict[str, Any] = Field(default_factory=dict)
    extractionQc: Dict[str, Any] = Field(default_factory=dict)


class ArchiveSampleTaskInput(BaseModel):
    """Input for sample.archive_sample (archive FASTQs, QC JSON, HDF5 to object storage)."""

    model_config = ConfigDict(extra="forbid")

    tool: str = "SampleArchive"
    sampleId: str
    sampleDir: str
    sampleDestination: SampleDestinationLocation | None = None
    h5Destination: SampleDestinationLocation | None = None
    mode: str = "full"
    rejectReason: Optional[str] = None
    alignmentQcPath: Optional[str] = None
    qcPath: Optional[str] = None
    projectPath: Optional[str] = None
    h5Files: Optional[List[str]] = None


class ArchiveSampleTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: str
    archiveMode: str = "full"
    rejectReason: Optional[str] = None
    uploadedFiles: List[str] = Field(default_factory=list)
    skippedFiles: List[str] = Field(default_factory=list)
    remotePrefix: str = ""
    uploadedCount: int = 0
    skippedCount: int = 0
    sampleArchived: bool = False
    archiveManifestPath: Optional[str] = None


class UploadH5TaskInput(ArchiveSampleTaskInput):
    """Deprecated alias — use ArchiveSampleTaskInput."""

    tool: str = "SampleUploadH5"


class UploadH5TaskOutput(ArchiveSampleTaskOutput):
    """Deprecated alias — use ArchiveSampleTaskOutput."""


class MethylExtractTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: Optional[str] = None
    h5Files: List[str] = Field(default_factory=list)


class ValidationPlanTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = "ok"
    context_json: Dict[str, Any] = Field(default_factory=dict)
    iterations: List[Dict[str, Any]] = Field(default_factory=list)
    n_iterations: int = 0
    projectPath: Optional[str] = None


class ValidationTaskInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    tool: Optional[str] = None
    projectPath: Optional[str] = None
    project: Optional[str] = None
    monteCarloRunsRoot: Optional[str] = None
    outputDir: Optional[str] = None
    stableDmpCsv: Optional[str] = None
    productionOutputDir: Optional[str] = None
    sourceRunDir: Optional[str] = None
    targetRunDir: Optional[str] = None
    runDir: Optional[str] = None
    bundleDir: Optional[str] = None
    bundleH5: Optional[str] = None
    backend: Optional[str] = None
    backends: Optional[List[str]] = None
    selectionMetric: Optional[str] = None
    selectionStat: Optional[str] = None
    modelMcRoot: Optional[str] = None
    featureIterations: Optional[int] = None
    qualityIterations: Optional[int] = None


class ValidationTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = "ok"
    summary: Dict[str, Any] = Field(default_factory=dict)


class TaskErrorOutput(BaseModel):
    """Worker failure payload on submit with result_code < 0."""

    model_config = ConfigDict(extra="allow")

    error: str
    capability: Optional[str] = None
