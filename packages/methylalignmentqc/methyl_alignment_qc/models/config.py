"""Pydantic config for MethylAlignmentQC; implemented in task 3."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


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
