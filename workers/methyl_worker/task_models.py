"""Pydantic models for workflow ACTION input_json / output_json payloads."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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

    model_config = ConfigDict(extra="allow")

    tool: str = "SampleDownloadFastq"
    sampleId: str
    sampleDir: str
    fastqSourceUri: str
    fastqUri: Optional[str] = None


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


class SampleIdOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: Optional[str] = None


class MethylQcTaskOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sampleId: str
    qcPath: str
    guardrails: Dict[str, Any] = Field(default_factory=dict)


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
