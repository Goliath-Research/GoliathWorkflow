"""Pydantic models for sample QC JSON payloads."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class QualityYield(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_reads: int
    pf_reads: int
    total_bases: int
    pf_bases: int
    q20_bases: int
    pf_q20_bases: int
    q30_bases: int
    pf_q30_bases: int
    q20_equivalent_yield: int
    pf_q20_equivalent_yield: int


class MeanQualityByCycle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cycle: List[int]
    mean_quality: List[float]


class QualityScoreDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Q: List[int]
    COUNT_OF_Q: List[int]


class BaseDistributionByCycle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cycle: List[int]
    PCT_A: List[float]
    PCT_C: List[float]
    PCT_G: List[float]
    PCT_T: List[float]
    PCT_N: List[float]


class GCBiasSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at_dropout: float
    gc_dropout: float


class GCBiasDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    GC: List[int]
    WINDOWS: List[int]
    READ_STARTS: List[int]
    MEAN_BASE_QUALITY: List[float]
    NORMALIZED_COVERAGE: List[float]
    ERROR_BAR: List[float]


class InsertSizeMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    median_insert_size: int
    mode_insert_size: int
    mean_insert_size: float
    standard_deviation: float
    read_pairs: int
    width_of_10_percent: int
    width_of_20_percent: int
    width_of_30_percent: int
    width_of_40_percent: int
    width_of_50_percent: int
    width_of_60_percent: int
    width_of_70_percent: int
    width_of_80_percent: int
    width_of_90_percent: int
    width_of_95_percent: int
    width_of_99_percent: int


class InsertSizeHistogram(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    insert_size: List[int]
    pair_orientation: List[str]
    all_reads_fr_count: List[int] = Field(alias="All_Reads.fr_count")
    VALUE: List[float] = Field(default_factory=list)
    all_sets: List[int] = Field(default_factory=list)
    optical_sets: List[int] = Field(default_factory=list)
    non_optical_sets: List[int] = Field(default_factory=list)


class ErrorSummaries(BaseModel):
    model_config = ConfigDict(extra="forbid")
    REF: List[str]
    ALT: List[str]
    COUNT: List[int]
    RATE: List[float]
    QSCORE: List[int]


class ArtifactSummaries(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ARTIFACT_NAME: List[str]
    TOTAL_QSCORE: List[int]
    WORST_CXT: List[str]
    WORST_CXT_QSCORE: List[int]


class DuplicationMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    LIBRARY: str
    UNPAIRED_READS_EXAMINED: int
    READ_PAIRS_EXAMINED: int
    SECONDARY_OR_SUPPLEMENTARY_RDS: int
    UNMAPPED_READS: int
    UNPAIRED_READ_DUPLICATES: int
    READ_PAIR_DUPLICATES: int
    READ_PAIR_OPTICAL_DUPLICATES: int
    PERCENT_DUPLICATION: float
    ESTIMATED_LIBRARY_SIZE: int


class DuplicationHistogram(BaseModel):
    model_config = ConfigDict(extra="forbid")
    BIN: List[float]
    VALUE: List[float]
    all_sets: List[int] = Field(default_factory=list)
    optical_sets: List[int] = Field(default_factory=list)
    non_optical_sets: List[int] = Field(default_factory=list)


class ConversionLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    program: str
    version: str
    start_time: str
    end_time: str
    total_time: str


class SummaryStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_reads: int
    duplication_rate: float
    estimated_library_size: int
    duplicate_reads: int
    optical_duplicates: int


class GuardrailMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float
    normal_range: str
    passed: bool = Field(alias="pass")
    message: str


class FragmentomicsMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: str
    median_insert_size: int
    short_fragment_fraction: float
    long_fragment_fraction: float
    nucleosome_peak_bp: Optional[int] = None
    short_fragment_max_bp: int
    nucleosome_peak_bp_min: int
    nucleosome_peak_bp_max: int


class FragmentomicsGuardrailDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    median_insert_bp: GuardrailMetric
    nucleosome_peak_bp: GuardrailMetric
    short_fragment_fraction: GuardrailMetric


class GuardrailDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pf_percent: GuardrailMetric
    q30_percent: GuardrailMetric
    mean_quality: GuardrailMetric
    min_quality_post20: GuardrailMetric
    at_dropout: GuardrailMetric
    gc_dropout: GuardrailMetric
    median_insert_bp: GuardrailMetric
    deamination_qscore: GuardrailMetric
    oxog_qscore: GuardrailMetric
    fragmentomics: Optional[FragmentomicsGuardrailDetails] = None


class GuardrailReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: str
    overall_pass: bool
    details: GuardrailDetails
    recommendation: str
    next_steps: str


class ParabricksMetricsPayload(BaseModel):
    """Canonical Parabricks metrics payload used as base export content."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str
    quality_yield: QualityYield
    mean_quality_by_cycle: MeanQualityByCycle
    quality_score_distribution: QualityScoreDistribution
    base_distribution_by_cycle: BaseDistributionByCycle
    gc_bias_summary: GCBiasSummary
    gc_bias_details: GCBiasDetails
    insert_size_metrics: InsertSizeMetrics
    insert_size_histogram: InsertSizeHistogram
    error_summaries: ErrorSummaries
    pre_adapter_summaries: ArtifactSummaries
    bait_bias_summaries: ArtifactSummaries
    conversion_log: ConversionLog
    duplication_metrics: Optional[List[DuplicationMetric]] = None
    duplication_histogram: Optional[DuplicationHistogram] = None


class ExportedSampleQCPayload(ParabricksMetricsPayload):
    """Final exported per-sample QC JSON."""

    model_config = ConfigDict(extra="forbid")

    duplication_metrics: List[DuplicationMetric]
    duplication_histogram: DuplicationHistogram
    summary_stats: SummaryStats
    guardrails: GuardrailReport
    fragmentomics_metrics: Optional[FragmentomicsMetrics] = None
