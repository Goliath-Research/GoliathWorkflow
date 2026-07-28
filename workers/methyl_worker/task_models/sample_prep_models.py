"""Strict Pydantic models for sample-prep workflow actions."""

from __future__ import annotations

from typing import List, Literal, Optional

from methyl_domain.fastq_storage import FastqSourceLocation
from methyl_domain.sample_storage import SampleDestinationLocation
from pydantic import BaseModel, ConfigDict, Field

from .base import ActionOutputBase


class DownloadFastqTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "SampleDownloadFastq"
    sampleId: str
    sampleDir: str
    fastqSource: FastqSourceLocation
    projectPath: Optional[str] = Field(
        default=None,
        description="Study project path for provenance/logging only; not a config source.",
    )
    executionScopeId: Optional[str] = Field(
        default=None,
        description="Baked execution scope id from instance finalize (provenance).",
    )
    resolvedConfig: Optional[dict] = Field(
        default=None,
        description="Merged actionConfig slice (may include storage_transfer knobs).",
    )


class ParabricksFq2bamTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "ParabricksFq2Bam"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = Field(
        default=None,
        description="Study project path for provenance/logging only; not a config source.",
    )
    project: Optional[str] = Field(
        default=None,
        description="Legacy alias of projectPath from older input templates (provenance only).",
    )
    executionScopeId: Optional[str] = Field(
        default=None,
        description="Baked execution scope id from instance finalize (provenance).",
    )
    resolvedConfig: Optional[dict] = Field(
        default=None,
        description="Merged actionConfig.parabricks baked at instance configuration.",
    )
    forceRealign: Optional[bool] = None
    alignmentPass: Optional[str] = None
    remediationReason: Optional[str] = None
    workflowNodeKey: Optional[str] = None


class ParabricksGiraffeTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "ParabricksGiraffe"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = Field(
        default=None,
        description="Study project path for provenance/logging only; not a config source.",
    )
    project: Optional[str] = Field(
        default=None,
        description="Legacy alias of projectPath from older input templates (provenance only).",
    )
    executionScopeId: Optional[str] = Field(
        default=None,
        description="Baked execution scope id from instance finalize (provenance).",
    )
    resolvedConfig: Optional[dict] = Field(
        default=None,
        description="Merged actionConfig.parabricks baked at instance configuration.",
    )
    forceRealign: Optional[bool] = None
    alignmentPass: Optional[str] = None
    remediationReason: Optional[str] = None
    workflowNodeKey: Optional[str] = None


class MethylGrapherGraphIndexFiles(BaseModel):
    """One converted-graph Giraffe index set (C2T or G2A)."""

    model_config = ConfigDict(extra="forbid")

    gbz: Optional[str] = Field(default=None, description="Path to .gbz graph index")
    dist: Optional[str] = Field(default=None, description="Path to Giraffe .dist index")
    min: Optional[str] = Field(
        default=None, description="Path to Giraffe minimizer (.min / .withzip.min)"
    )
    zipcodes: Optional[str] = Field(default=None, description="Path to Giraffe zipcodes index")


class MethylGrapherReadLevelConfig(BaseModel):
    """Read-level pattern extraction knobs under actionConfig.methylgrapher_wgbs.read_level."""

    model_config = ConfigDict(extra="forbid")

    enabled: Optional[bool] = Field(
        default=None,
        description="Enable read-level / pattern extraction. Operator-set per site/profile.",
    )
    tile_size: Optional[int] = Field(
        default=None,
        ge=1,
        description="Pattern tile size (bp). Operator-set per site/profile.",
    )


class MethylGrapherWgbsStepConfig(BaseModel):
    """Operator-tunable methylGrapher WGBS pangenome knobs (actionConfig.methylgrapher_wgbs).

    Asset paths are site-pinned under ``/work/genomes/pangenome/.../d9-bs/...`` and
    baked into task ``resolvedConfig`` at instance configuration. Workers must not
    re-read site/profile manifests for these values when ``resolvedConfig`` is present.
    """

    model_config = ConfigDict(extra="forbid")

    alignment_mode: Optional[str] = Field(
        default=None,
        description="Must be pangenome_wgbs when this section is used. Set at site/profile/procedure.",
    )
    directional: Optional[bool] = Field(
        default=None,
        description="Directional WGBS library (methylGrapher -directional). Operator-set per site/profile.",
    )
    threads: Optional[int] = Field(
        default=None,
        ge=1,
        description="Worker threads for methylGrapher/vg. Operator-set per site/profile.",
    )
    image: Optional[str] = Field(
        default=None,
        description="Pinned methylGrapher(+vg) Docker image ref/digest. Or METHYL_METHYLGRAPHER_IMAGE.",
    )
    image_digest: Optional[str] = Field(
        default=None,
        description="Optional immutable digest recorded in CAAS fingerprints / provenance.",
    )
    methylgrapher_version: Optional[str] = Field(
        default=None,
        description="Pinned methylGrapher version string for provenance / CAAS.",
    )
    vg_version: Optional[str] = Field(
        default=None,
        description="Pinned vg version string for provenance / CAAS (must match index builder).",
    )
    index_prefix: Optional[str] = Field(
        default=None,
        description="PrepareGenome-style index prefix under the BS bundle (e.g. .../hprc-d9-bs).",
    )
    c2t: Optional[MethylGrapherGraphIndexFiles] = Field(
        default=None, description="C-to-T converted graph Giraffe indexes."
    )
    g2a: Optional[MethylGrapherGraphIndexFiles] = Field(
        default=None, description="G-to-A converted graph Giraffe indexes."
    )
    original_gbz: Optional[str] = Field(
        default=None,
        description="Unconverted graph GBZ used for MethylCall / coordinate provenance.",
    )
    ref_paths: Optional[str] = Field(
        default=None, description="GRCh38 ref-paths file for surjection / linear coordinates."
    )
    cpg_tsv: Optional[str] = Field(
        default=None, description="methylGrapher {prefix}cpg.tsv (graph CpG registry)."
    )
    node_replacement_json: Optional[str] = Field(
        default=None, description="Optional node-replacement JSON from PrepareGenome."
    )
    linear_ref_fasta: Optional[str] = Field(
        default=None,
        description="Linear GRCh38 FASTA matching ref_paths (QC BAM / extraction contracts).",
    )
    cg_only: Optional[bool] = Field(
        default=None, description="MethylCall -cg_only. Operator-set per site/profile."
    )
    read_level: Optional[MethylGrapherReadLevelConfig] = Field(
        default=None,
        description="Read-level pattern extraction knobs. Operator-set per site/profile.",
    )
    contexts: Optional[List[str]] = Field(
        default=None, description="Methylation contexts to emit as {chrom}-{ctx}.h5 (e.g. CG)."
    )


class MethylGrapherWgbsAlignTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "MethylGrapherWgbsAlign"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = None
    project: Optional[str] = Field(
        default=None,
        description="Legacy alias of projectPath from older input templates (provenance only).",
    )
    executionScopeId: Optional[str] = None
    forceRealign: Optional[bool] = None
    alignmentPass: Optional[str] = None
    remediationReason: Optional[str] = None
    workflowNodeKey: Optional[str] = None
    resolvedConfig: Optional[MethylGrapherWgbsStepConfig] = Field(
        default=None,
        description="Merged actionConfig.methylgrapher_wgbs (assets + tool pins).",
    )


class MethylGrapherWgbsExtractTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "MethylGrapherWgbsExtract"
    sampleId: str
    sampleDir: str
    projectPath: str
    project: Optional[str] = Field(
        default=None,
        description="Legacy alias of projectPath from older input templates (provenance only).",
    )
    executionScopeId: Optional[str] = None
    forceRealign: Optional[bool] = None
    resolvedConfig: Optional[MethylGrapherWgbsStepConfig] = Field(
        default=None,
        description="Merged actionConfig.methylgrapher_wgbs (+ extract overlays).",
    )


class DemultiplexTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "SampleDemultiplex"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = None
    project: Optional[str] = Field(
        default=None,
        description="Legacy alias of projectPath from older input templates (provenance only).",
    )
    executionScopeId: Optional[str] = None
    barcodeTsv: Optional[str] = None
    skipDemultiplex: Optional[bool] = None
    resolvedConfig: Optional[dict] = Field(
        default=None,
        description="Merged demultiplex actionConfig (barcode_tsv, barcode_len, skip).",
    )


class DockerAlignTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "SampleDockerAlign"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = None
    project: Optional[str] = Field(
        default=None,
        description="Legacy alias of projectPath from older input templates (provenance only).",
    )
    executionScopeId: Optional[str] = None
    forceRealign: Optional[bool] = None
    alignmentPass: Optional[str] = None
    remediationReason: Optional[str] = None
    workflowNodeKey: Optional[str] = None
    resolvedConfig: Optional[dict] = Field(
        default=None,
        description="Merged docker_align actionConfig (image, argv, gpu_flags).",
    )


class TrimFastqTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "SampleTrimFastq"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = Field(
        default=None,
        description="Study project path for provenance/logging only; not a config source.",
    )
    executionScopeId: Optional[str] = Field(
        default=None,
        description="Baked execution scope id from instance finalize (provenance).",
    )
    trimFront1: Optional[int] = None
    trimTail1: Optional[int] = None
    trimFront2: Optional[int] = None
    trimTail2: Optional[int] = None
    remediationReason: Optional[str] = None


class RemediationTrigger(BaseModel):
    """Why a QC re-evaluation was scheduled, bound by the program's realign branch."""

    model_config = ConfigDict(extra="forbid")

    disposition: Optional[str] = Field(
        default=None,
        description="Screening disposition that triggered remediation (e.g. REALIGN_TRIM).",
    )
    trimFront1: Optional[int] = Field(default=None, ge=0)
    trimTail1: Optional[int] = Field(default=None, ge=0)
    trimFront2: Optional[int] = Field(default=None, ge=0)
    trimTail2: Optional[int] = Field(default=None, ge=0)
    priorNode: Optional[str] = Field(
        default=None,
        description="Node key of the QC attempt that produced the disposition.",
    )


class MethylQcTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "MethylAlignmentQc"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = None
    project: Optional[str] = Field(
        default=None,
        description="Legacy alias of projectPath from older input templates (provenance only).",
    )
    executionScopeId: Optional[str] = None
    primaryAnalyte: Optional[str] = None
    resolvedConfig: Optional[dict] = Field(
        default=None,
        description="Merged actionConfig.alignment_qc baked at instance configuration.",
    )
    alignmentPass: Optional[str] = None
    qcAttempt: Optional[int] = None
    qcAttemptReason: Optional[str] = None
    remediationTrigger: Optional[RemediationTrigger] = Field(
        default=None,
        description="Set on retry QC nodes so the attempt record keeps the trim provenance.",
    )
    workflowNodeKey: Optional[str] = None


class FragmentomicsTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "MethylFragmentomics"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = None
    project: Optional[str] = Field(
        default=None,
        description="Legacy alias of projectPath from older input templates (provenance only).",
    )
    executionScopeId: Optional[str] = None
    resolvedConfig: Optional[dict] = None


class MethylExtractTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "MethylExtract"
    sampleId: str
    sampleDir: str
    projectPath: str
    project: Optional[str] = Field(
        default=None,
        description="Legacy alias of projectPath from older input templates (provenance only).",
    )
    executionScopeId: Optional[str] = None
    resolvedConfig: Optional[dict] = Field(
        default=None,
        description="Merged actionConfig.methyl_extract baked at instance configuration.",
    )


class ExtractionQcTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "MethylExtractionQc"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = None
    project: Optional[str] = Field(
        default=None,
        description="Legacy alias of projectPath from older input templates (provenance only).",
    )
    executionScopeId: Optional[str] = None
    resolvedConfig: Optional[dict] = None


class DeleteFastqsTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "SampleDeleteFastqs"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = Field(
        default=None,
        description="Study project path for provenance/logging only; not a config source.",
    )
    executionScopeId: Optional[str] = Field(
        default=None,
        description="Baked execution scope id from instance finalize (provenance).",
    )


class DeleteBamTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "SampleDeleteBam"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = Field(
        default=None,
        description="Study project path for provenance/logging only; not a config source.",
    )
    executionScopeId: Optional[str] = Field(
        default=None,
        description="Baked execution scope id from instance finalize (provenance).",
    )


class QcFailedTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = "SampleMarkFailed"
    sampleId: str
    sampleDir: str
    projectPath: Optional[str] = Field(
        default=None,
        description="Study project path for provenance/logging only; not a config source.",
    )
    executionScopeId: Optional[str] = Field(
        default=None,
        description="Baked execution scope id from instance finalize (provenance).",
    )
    reason: Optional[str] = None


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
    executionScopeId: Optional[str] = Field(
        default=None,
        description="Baked execution scope id from instance finalize (provenance).",
    )
    h5Files: Optional[List[str]] = None


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


class MethylGrapherWgbsAlignTaskOutput(ActionOutputBase):
    sampleId: Optional[str] = None
    bamPath: Optional[str] = None
    gafPath: Optional[str] = None
    metricsJson: Optional[str] = None
    qcMetricsTar: Optional[str] = None
    dedupMetricsPath: Optional[str] = None
    conversionReportPath: Optional[str] = None


class DemultiplexTaskOutput(ActionOutputBase):
    sampleId: Optional[str] = None
    fastqR1: Optional[str] = None
    fastqR2: Optional[str] = None
    n_reads_kept: Optional[int] = None
    barcode: Optional[str] = None
    skipped: bool = False


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
    archiveSkipped: bool = False
    skipReason: Optional[str] = None
    missingConfiguration: List[str] = Field(default_factory=list)
    archiveManifestPath: Optional[str] = None


class MethylExtractTaskOutput(ActionOutputBase):
    sampleId: Optional[str] = None
    h5Files: List[str] = Field(default_factory=list)
    n_h5_files: int = 0
