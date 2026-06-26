"""Pydantic models for sample QC JSON payloads."""

from __future__ import annotations

from typing import Dict, List, Optional

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


class AlignmentStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reads_examined: int
    unmapped_reads: int
    secondary_supplementary_reads: int
    mapping_rate: float
    secondary_supplementary_rate: float
    gc_coverage_uniformity: Optional[float] = None


class AlignmentFlagstat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_reads: Optional[int] = None
    mapped_reads: Optional[int] = None
    properly_paired_reads: Optional[int] = None
    supplementary_reads: Optional[int] = None
    secondary_reads: Optional[int] = None
    duplicate_reads: Optional[int] = None
    properly_paired_rate: Optional[float] = None
    supplementary_rate: Optional[float] = None
    mapped_rate: Optional[float] = None


class GuardrailMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float
    normal_range: str
    passed: bool = Field(alias="pass")
    message: str


class BisulfiteConversionMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    measurement_source: str
    conversion_rate_pct: Optional[float] = None
    non_cpg_methylation_pct: Optional[float] = None
    deamination_qscore: Optional[int] = None
    min_conversion_rate_pct: float
    max_non_cpg_methylation_pct: float
    notes: Optional[str] = None


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


class TrimSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read: int
    end: str
    bases: int


class QcScreeningReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disposition: str
    quality_pattern: Optional[str] = None
    read_length: int
    r2_start_cycle: int
    trim_front1: int = 0
    trim_tail1: int = 0
    trim_front2: int = 0
    trim_tail2: int = 0
    trim_spec: Optional[TrimSpec] = None
    r2_start_mean_quality: Optional[float] = None
    r2_recovery_mean_quality: Optional[float] = None
    dip_regions: List[Dict[str, int]] = Field(default_factory=list)
    message: str
    bad_cycle_start: Optional[int] = None
    bad_cycle_end: Optional[int] = None
    n_cycles: Optional[int] = None


class QcAttemptRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt: int
    evaluated_at_utc: str
    alignment_pass: str
    reason: str
    trigger_disposition: Optional[str] = None
    trigger_action: Optional[str] = None
    trim_front1: Optional[int] = None
    trim_tail1: Optional[int] = None
    trim_front2: Optional[int] = None
    trim_tail2: Optional[int] = None
    overall_pass: bool
    disposition: str
    failed_guardrails: List[str] = Field(default_factory=list)
    workflow_node_key: Optional[str] = None


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
    duplication_rate: Optional[GuardrailMetric] = None
    min_pf_reads: Optional[GuardrailMetric] = None
    mapping_rate: Optional[GuardrailMetric] = None
    secondary_supplementary_rate: Optional[GuardrailMetric] = None
    gc_coverage_uniformity: Optional[GuardrailMetric] = None
    properly_paired_rate: Optional[GuardrailMetric] = None
    supplementary_rate_flagstat: Optional[GuardrailMetric] = None
    fragmentomics: Optional[FragmentomicsGuardrailDetails] = None
    bisulfite_conversion: Optional[Dict[str, GuardrailMetric]] = None


class GuardrailReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: str
    overall_pass: bool
    details: GuardrailDetails
    recommendation: str
    next_steps: str
    screening: Optional[QcScreeningReport] = None


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
    alignment_stats: Optional[AlignmentStats] = None
    alignment_flagstat: Optional[AlignmentFlagstat] = None
    fragmentomics_metrics: Optional[FragmentomicsMetrics] = None
    bisulfite_conversion_metrics: Optional[BisulfiteConversionMetrics] = None
    qc_history: Optional[List[QcAttemptRecord]] = None
    sample_prep_log_path: Optional[str] = None
