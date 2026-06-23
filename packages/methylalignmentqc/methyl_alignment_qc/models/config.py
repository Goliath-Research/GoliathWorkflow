"""Pydantic config for MethylAlignmentQC; implemented in task 3."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class CycleScreeningConfig(BaseModel):
    """Per-cycle read-end screening for remediation dispositions."""

    enabled: bool = Field(default=True)
    read_length: Optional[int] = Field(
        default=None,
        ge=1,
        description="Override read length; default inferred as max_cycle // 2.",
    )
    r2_start_window_cycles: int = Field(default=5, ge=1)
    recovery_cycles: int = Field(default=10, ge=1)
    r2_quality_threshold: float = Field(default=30.0)
    max_trim_bases: int = Field(default=8, ge=1)
    multi_region_min_separate_dips: int = Field(default=2, ge=2)
    read_edge_window: int = Field(default=10, ge=1)
    broad_bad_cycle_count: int = Field(default=8, ge=1)
    localized_max_span: int = Field(default=6, ge=1)


class OptionalGuardrailsConfig(BaseModel):
    """Config-gated guardrails beyond core WGBS Parabricks checks."""

    duplication_rate_max: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="When set, fail when summary_stats.duplication_rate exceeds this.",
    )
    min_pf_reads: Optional[int] = Field(
        default=None,
        ge=1,
        description="When set, fail when quality_yield.pf_reads is below this.",
    )


class BisulfiteConversionConfig(BaseModel):
    """Quantitative bisulfite conversion QC (sidecar JSON or deamination proxy)."""

    enabled: bool = Field(default=False)
    source: Literal["sidecar", "deamination_proxy", "auto"] = Field(
        default="auto",
        description="auto: use sidecar when present, else deamination proxy.",
    )
    sidecar_filename: str = Field(
        default="bisulfite_conversion.json",
        description="Per-sample file in sample dir with conversion_rate_pct and optional non_cpg_methylation_pct.",
    )
    min_conversion_rate_pct: float = Field(
        default=99.0,
        ge=0.0,
        le=100.0,
        description="Minimum acceptable conversion rate (%) when sidecar supplies it.",
    )
    max_non_cpg_methylation_pct: float = Field(
        default=2.0,
        ge=0.0,
        le=100.0,
        description="Maximum acceptable non-CpG methylation (%) when sidecar supplies it.",
    )
    max_deamination_qscore_proxy: int = Field(
        default=30,
        ge=0,
        description="Pass deamination qscore proxy when <= this value.",
    )


class FragmentomicsConfig(BaseModel):
    """Optional cfDNA / fragment-length QC derived from insert-size histograms."""

    enabled: bool = Field(default=False, description="Compute fragmentomics metrics and guardrails.")
    profile: Literal["off", "cfdna", "wgbs"] = Field(
        default="off",
        description="Guardrail profile: cfdna adds nucleosome/short-fragment checks; wgbs metrics only.",
    )
    short_fragment_max_bp: int = Field(default=150, ge=1, description="Fragments at or below this size are 'short'.")
    long_fragment_min_bp: int = Field(default=300, ge=1, description="Fragments at or above this size are 'long'.")
    nucleosome_peak_bp_min: int = Field(default=140, ge=1)
    nucleosome_peak_bp_max: int = Field(default=200, ge=1)
    median_insert_min_bp: int = Field(default=120, ge=1)
    median_insert_max_bp: int = Field(default=220, ge=1)
    max_short_fragment_fraction: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Fail cfDNA guardrail when short-fragment fraction exceeds this.",
    )

    def resolved_profile(self) -> str:
        if not self.enabled:
            return "off"
        return str(self.profile or "off").strip().lower()

    def is_active(self) -> bool:
        return self.enabled and self.resolved_profile() != "off"


class AlignmentQCConfig(BaseModel):
    """Config for alignment QC step: sample paths and output directory."""

    sample_paths: List[str] = Field(..., description="List of sample directory paths")
    output_dir: str = Field(..., description="Output directory; one JSON per sample as {output_dir}/{basename}.json")
    validate_schema: bool = Field(True, description="Whether to validate each sample JSON against schema")
    genome_fasta: Optional[str] = Field(
        None,
        description=(
            "Path to the reference genome FASTA (e.g. hg38.fa). This is the project's "
            "shared genome reference; downstream consumers such as the MethylEnricher "
            "CIS-BP promoter scan default to this value."
        ),
    )
    fragmentomics: Optional[FragmentomicsConfig] = Field(
        default=None,
        description="Optional fragment-length / cfDNA metrics from insert-size histogram.",
    )
    auto_profile_from_analyte: bool = Field(
        default=False,
        description=(
            "When true, enable fragmentomics profile cfdna if "
            "step_config.validation.regulatory.primary_analyte is cfdna."
        ),
    )
    bisulfite_conversion: Optional[BisulfiteConversionConfig] = Field(
        default=None,
        description="Optional bisulfite conversion rate QC from per-sample sidecar files.",
    )
    cycle_screening: Optional[CycleScreeningConfig] = Field(
        default=None,
        description="Read 2 start cycle screening for remediation dispositions.",
    )
    optional_guardrails: Optional[OptionalGuardrailsConfig] = Field(
        default_factory=lambda: OptionalGuardrailsConfig(duplication_rate_max=0.30),
        description="Additional guardrails (duplication rate, min PF reads).",
    )

    @field_validator("cycle_screening", mode="before")
    @classmethod
    def _coerce_cycle_screening(cls, value):  # noqa: ANN001
        if value is None:
            return None
        if isinstance(value, CycleScreeningConfig):
            return value
        if isinstance(value, dict):
            return CycleScreeningConfig.model_validate(value)
        return value

    @field_validator("optional_guardrails", mode="before")
    @classmethod
    def _coerce_optional_guardrails(cls, value):  # noqa: ANN001
        if value is None:
            return None
        if isinstance(value, OptionalGuardrailsConfig):
            return value
        if isinstance(value, dict):
            return OptionalGuardrailsConfig.model_validate(value)
        return value

    @field_validator("fragmentomics", mode="before")
    @classmethod
    def _coerce_fragmentomics(cls, value):  # noqa: ANN001
        if value is None:
            return None
        if isinstance(value, FragmentomicsConfig):
            return value
        if isinstance(value, dict):
            return FragmentomicsConfig.model_validate(value)
        return value

    @field_validator("bisulfite_conversion", mode="before")
    @classmethod
    def _coerce_bisulfite(cls, value):  # noqa: ANN001
        if value is None:
            return None
        if isinstance(value, BisulfiteConversionConfig):
            return value
        if isinstance(value, dict):
            return BisulfiteConversionConfig.model_validate(value)
        return value
