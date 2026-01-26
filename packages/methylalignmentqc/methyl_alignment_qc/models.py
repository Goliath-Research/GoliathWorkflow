from pydantic import BaseModel, Field
from typing import List

class QualityYield(BaseModel):
    total_reads: int = Field(..., description="Total sequenced reads")
    pf_reads: int = Field(..., description="Passing Filter reads")
    total_bases: int = Field(..., description="Total bases sequenced")
    pf_bases: int = Field(..., description="Passing Filter bases")
    q20_bases: int = Field(..., description="Bases >= Q20")
    pf_q20_bases: int = Field(..., description="PF Bases >= Q20")
    q30_bases: int = Field(..., description="Bases >= Q30")
    pf_q30_bases: int = Field(..., description="PF Bases >= Q30")
    q20_equivalent_yield: int = Field(..., description="Q20 equivalent yield")
    pf_q20_equivalent_yield: int = Field(..., description="PF Q20 equivalent yield")

class MeanQualityByCycle(BaseModel):
    cycle: List[int]
    mean_quality: List[float]

class QualityScoreDistribution(BaseModel):
    quality_score: List[int] = Field(alias="Q")
    count: List[int] = Field(alias="COUNT_OF_Q")

class BaseDistributionByCycle(BaseModel):
    cycle: List[int]
    pct_a: List[float] = Field(alias="PCT_A")
    pct_c: List[float] = Field(alias="PCT_C")
    pct_g: List[float] = Field(alias="PCT_G")
    pct_t: List[float] = Field(alias="PCT_T")
    pct_n: List[float] = Field(alias="PCT_N")

class GCBiasSummary(BaseModel):
    at_dropout: float = Field(..., description="AT dropout percentage")
    gc_dropout: float = Field(..., description="GC dropout percentage")

class GCBiasDetail(BaseModel):
    gc: List[int] = Field(alias="GC")
    windows: List[int] = Field(alias="WINDOWS")
    read_starts: List[int] = Field(alias="READ_STARTS")
    mean_base_quality: List[float] = Field(alias="MEAN_BASE_QUALITY")
    normalized_coverage: List[float] = Field(alias="NORMALIZED_COVERAGE")
    error_bar: List[float] = Field(alias="ERROR_BAR")

class InsertSizeMetrics(BaseModel):
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
    insert_size: List[int] = Field(alias="insert_size")
    pair_orientation: List[str] = Field(alias="pair_orientation")
    all_reads_count: List[int] = Field(alias="All_Reads.fr_count")

class ErrorSummary(BaseModel):
    ref: List[str] = Field(alias="REF")
    alt: List[str] = Field(alias="ALT")
    count: List[int] = Field(alias="COUNT")
    rate: List[float] = Field(alias="RATE")
    qscore: List[int] = Field(alias="QSCORE")

class ArtifactSummary(BaseModel):
    artifact_name: List[str] = Field(alias="ARTIFACT_NAME")
    total_qscore: List[int] = Field(alias="TOTAL_QSCORE")
    worst_cxt: List[str] = Field(alias="WORST_CXT")
    worst_cxt_qscore: List[int] = Field(alias="WORST_CXT_QSCORE")

class AlignmentQC(BaseModel):
    sample_id: str
    quality_yield: QualityYield
    mean_quality_by_cycle: MeanQualityByCycle
    quality_score_distribution: QualityScoreDistribution
    base_distribution_by_cycle: BaseDistributionByCycle
    gc_bias_summary: GCBiasSummary
    gc_bias_details: GCBiasDetail
    insert_size_metrics: InsertSizeMetrics
    insert_size_histogram: InsertSizeHistogram
    error_summaries: ErrorSummary
    pre_adapter_summaries: ArtifactSummary
    bait_bias_summaries: ArtifactSummary