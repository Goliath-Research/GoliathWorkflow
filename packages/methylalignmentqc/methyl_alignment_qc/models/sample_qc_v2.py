"""Row-oriented (V2) Pydantic models for exported sample QC JSON."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .sample_qc import (
    ConversionLog,
    DuplicationMetric,
    BisulfiteConversionMetrics,
    FragmentomicsMetrics,
    GCBiasSummary,
    GuardrailReport,
    InsertSizeMetrics,
    QcAttemptRecord,
    QualityYield,
    SummaryStats,
)


class QCV2Producer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package: str = Field(description="Producer package name")
    version: str = Field(description="Producer package version")


class QCV2Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_name: str = Field(default="methylalignmentqc.sample_qc")
    schema_version: str = Field(default="2.0.0")
    exported_at_utc: str = Field(description="ISO-8601 UTC timestamp when V2 export was produced")
    producer: QCV2Producer
    qc_attempt: Optional[int] = Field(default=None, description="Current QC evaluation attempt number")


class MeanQualityByCycleRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cycle: int
    mean_quality: float


class MeanQualityByCycleV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: List[MeanQualityByCycleRow]


class QualityScoreDistributionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: int
    count_of_q: int


class QualityScoreDistributionV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: List[QualityScoreDistributionRow]


class BaseDistributionByCycleRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cycle: int
    pct_a: float
    pct_c: float
    pct_g: float
    pct_t: float
    pct_n: float


class BaseDistributionByCycleV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: List[BaseDistributionByCycleRow]


class GCBiasDetailsRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gc: int
    windows: int
    read_starts: int
    mean_base_quality: float
    normalized_coverage: float
    error_bar: float


class GCBiasDetailsV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: List[GCBiasDetailsRow]


class InsertSizeHistogramRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    insert_size: int
    pair_orientation: str
    all_reads_fr_count: int
    value: Optional[float] = None
    all_sets: Optional[int] = None
    optical_sets: Optional[int] = None
    non_optical_sets: Optional[int] = None


class InsertSizeHistogramV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: List[InsertSizeHistogramRow]


class ErrorSummariesRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    alt: str
    count: int
    rate: float
    qscore: int


class ErrorSummariesV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: List[ErrorSummariesRow]


class ArtifactSummariesRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_name: str
    total_qscore: int
    worst_cxt: str
    worst_cxt_qscore: int


class ArtifactSummariesV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: List[ArtifactSummariesRow]


class DuplicationHistogramRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bin: float
    value: float
    all_sets: Optional[int] = None
    optical_sets: Optional[int] = None
    non_optical_sets: Optional[int] = None


class DuplicationHistogramV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: List[DuplicationHistogramRow]


class ExportedSampleQCV2Payload(BaseModel):
    """Row-oriented per-sample QC JSON (V2) for tools and Azure SQL OPENJSON."""

    model_config = ConfigDict(extra="forbid")

    metadata: QCV2Metadata
    sample_id: str
    quality_yield: QualityYield
    mean_quality_by_cycle: MeanQualityByCycleV2
    quality_score_distribution: QualityScoreDistributionV2
    base_distribution_by_cycle: BaseDistributionByCycleV2
    gc_bias_summary: GCBiasSummary
    gc_bias_details: GCBiasDetailsV2
    insert_size_metrics: InsertSizeMetrics
    insert_size_histogram: InsertSizeHistogramV2
    error_summaries: ErrorSummariesV2
    pre_adapter_summaries: ArtifactSummariesV2
    bait_bias_summaries: ArtifactSummariesV2
    conversion_log: ConversionLog
    duplication_metrics: List[DuplicationMetric]
    duplication_histogram: DuplicationHistogramV2
    summary_stats: SummaryStats
    guardrails: GuardrailReport
    fragmentomics_metrics: Optional[FragmentomicsMetrics] = None
    bisulfite_conversion_metrics: Optional[BisulfiteConversionMetrics] = None
    qc_history: Optional[List[QcAttemptRecord]] = None
    sample_prep_log_path: Optional[str] = None
