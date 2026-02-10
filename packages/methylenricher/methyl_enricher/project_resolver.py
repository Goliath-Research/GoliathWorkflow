"""
Resolve MethylEnricher paths from a pipeline project config.
Uses Pydantic only; no raw dict configs.
"""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from methyl_utils import load_project


class EnricherStepPaths(BaseModel):
    """Paths for the enricher step derived from a project (and optional overrides)."""

    input_file: str = Field(
        ...,
        description="Input combined gene CSV (e.g. mapper all-gene_name-combined.csv)",
    )
    output_dir: str = Field(
        ...,
        description="Output directory for enrichment results (enricher_dir)",
    )


def resolve_enricher_paths(
    project_path: Path,
    step_override_path: Optional[Path] = None,
    combined_csv_name: str = "all-gene_name-combined.csv",
) -> EnricherStepPaths:
    """
    Build enricher step paths from a project config.

    Input is the mapper combined CSV; output goes to enricher_dir.
    Optional step_override_path JSON can override input_file and/or output_dir.
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    input_file = paths.mapper_combined_csv
    output_dir = paths.enricher_dir

    overrides: dict = {}
    if step_override_path and step_override_path.exists():
        import json
        with open(step_override_path) as f:
            overrides = json.load(f)

    if overrides.get("input") is not None:
        input_file = overrides["input"]
    if overrides.get("input_file") is not None:
        input_file = overrides["input_file"]
    if overrides.get("output_dir") is not None:
        output_dir = overrides["output_dir"]
    if overrides.get("outdir") is not None:
        output_dir = overrides["outdir"]

    return EnricherStepPaths(input_file=input_file, output_dir=output_dir)
