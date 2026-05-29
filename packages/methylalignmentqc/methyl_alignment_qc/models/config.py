"""Pydantic config for MethylAlignmentQC; implemented in task 3."""

from typing import List, Optional

from pydantic import BaseModel, Field


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
