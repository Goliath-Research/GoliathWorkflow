"""Pydantic config for MethylAlignmentQC; implemented in task 3."""

from typing import List

from pydantic import BaseModel, Field


class AlignmentQCConfig(BaseModel):
    """Config for alignment QC step: sample paths and output directory."""

    sample_paths: List[str] = Field(..., description="List of sample directory paths")
    output_dir: str = Field(..., description="Output directory; one JSON per sample as {output_dir}/{basename}.json")
    validate_schema: bool = Field(True, description="Whether to validate each sample JSON against schema")
