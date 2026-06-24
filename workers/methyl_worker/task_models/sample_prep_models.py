"""Strict Pydantic models for sample-prep workflow actions."""

from __future__ import annotations

from typing import List, Literal, Optional

from methyl_domain.fastq_storage import FastqSourceLocation
from methyl_domain.sample_storage import SampleDestinationLocation
from pydantic import BaseModel, ConfigDict, Field

from .base import ActionOutputBase


class SamplePrepTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sampleId: Optional[str] = None
    sampleDir: Optional[str] = None
    project: Optional[str] = None
    projectPath: Optional[str] = None
    reason: Optional[str] = None
    fastqUri: Optional[str] = None
    chromosomes: Optional[List[str]] = None


class DownloadFastqTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "SampleDownloadFastq"
    sampleId: str
    sampleDir: str
    fastqSource: FastqSourceLocation


class ParabricksFq2bamTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "ParabricksFq2Bam"
    sampleId: str
    sampleDir: str
    referenceFasta: str
    referenceGtf: Optional[str] = None
    parabricksImage: Optional[str] = None
    bwaThreads: Optional[int] = None


class MethylExtractTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class ArchiveSampleTaskInput(BaseModel):
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


class UploadH5TaskInput(ArchiveSampleTaskInput):
    tool: str = "SampleUploadH5"


class QcHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: int = 1
    reason: str = ""
    overall_pass: Optional[bool] = None
    disposition: Optional[str] = None


class ScreeningOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: Optional[str] = None
    trim_front1: int = 0
    trim_tail1: int = 0
    trim_front2: int = 0
    trim_tail2: int = 0
    message: Optional[str] = None


class GuardrailsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_pass: Optional[bool] = None
    screening: ScreeningOutput = Field(default_factory=ScreeningOutput)


class SampleIdOutput(ActionOutputBase):
    sampleId: Optional[str] = None


class DownloadFastqTaskOutput(ActionOutputBase):
    sampleId: Optional[str] = None
    fastqFiles: List[str] = Field(default_factory=list)
    n_files: int = 0


class ParabricksTaskOutput(ActionOutputBase):
    sampleId: Optional[str] = None
    bamPath: Optional[str] = None
    metricsJson: Optional[str] = None
    qcMetricsTar: Optional[str] = None


class TrimFastqTaskOutput(ActionOutputBase):
    sampleId: str
    trimFront1: str = "0"
    trimTail1: str = "0"
    trimFront2: str = "0"
    trimTail2: str = "0"
    trimmedR1: str
    trimmedR2: str
    logReason: str = ""


class MethylQcTaskOutput(ActionOutputBase):
    sampleId: str
    qcPath: str
    guardrails: GuardrailsOutput
    screening: ScreeningOutput
    qcHistory: List[QcHistoryEntry] = Field(default_factory=list)
    remediateAlignment: bool = False
    remediateR2Trim: bool = False


class FragmentomicsTaskOutput(ActionOutputBase):
    sampleId: str
    outputDir: str
    n_fragments: Optional[int] = None
    summary_path: Optional[str] = None


class MarkFailedTaskOutput(ActionOutputBase):
    sampleId: Optional[str] = None
    sampleDir: Optional[str] = None
    status: Literal["QC_FAILED"] = "QC_FAILED"
    reason: str = "alignment_qc_failed"


class DeleteTaskOutput(ActionOutputBase):
    sampleId: Optional[str] = None
    deleted: bool = True
    n_files_removed: int = 0


class ExtractionQcTaskOutput(ActionOutputBase):
    sampleId: str
    qcPath: str
    guardrails: GuardrailsOutput
    extraction_pass: Optional[bool] = None


class ArchiveSampleTaskOutput(ActionOutputBase):
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


class UploadH5TaskOutput(ArchiveSampleTaskOutput):
    pass


class MethylExtractTaskOutput(ActionOutputBase):
    sampleId: Optional[str] = None
    h5Files: List[str] = Field(default_factory=list)
    n_h5_files: int = 0
