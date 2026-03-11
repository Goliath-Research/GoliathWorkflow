"""
Resolve MethylEnricher paths from a pipeline project config.
Uses the same layout as MethylDetector/MethylMapper: when the project has multiple
groups, mapper outputs live under mapper/cancer/<label> and enricher should write
to enricher/cancer/<label> per group.
"""

from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from methyl_utils import load_project

DISEASE_SUBDIR_DEFAULT = "cancer"


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


def resolve_enricher_paths_per_cancer_group(
    project_path: Path,
    step_override_path: Optional[Path] = None,
    control_index: int = 0,
    disease_subdir: str = DISEASE_SUBDIR_DEFAULT,
    combined_csv_name: str = "all-gene_name-combined.csv",
) -> List[Tuple[EnricherStepPaths, str]]:
    """
    Build one EnricherStepPaths per comparison.
    When project uses control/disease + comparisons: one entry per get_comparisons().
    Otherwise: one per non-control group (flat groups).

    Returns:
        List of (EnricherStepPaths, comparison_label) for each comparison.
    """
    project = load_project(project_path)
    step_cfg = project.get_step_config("enricher") or {}
    if step_override_path and step_override_path.exists():
        import json
        with open(step_override_path) as f:
            overrides = json.load(f)
        step_cfg = {**step_cfg, **overrides}
    csv_name = step_cfg.get("combined_csv_name") or combined_csv_name

    if getattr(project, "uses_control_disease", lambda: False)():
        out: List[Tuple[EnricherStepPaths, str]] = []
        for spec in project.get_comparisons():
            comp_label = spec.comparison_label or spec.disease_group
            map_dir = project.get_mapper_output_dir(spec.control_group, spec.disease_group)
            enr_dir = project.get_enricher_output_dir(spec.control_group, spec.disease_group)
            input_file = str(Path(map_dir) / csv_name)
            out.append((EnricherStepPaths(input_file=input_file, output_dir=enr_dir), comp_label))
        return out

    paths = project.get_derived_paths()
    resolved = getattr(project, "get_resolved_groups", lambda: [])()
    if len(resolved) < 2:
        return []
    mapper_dir = Path(paths.mapper_dir)
    enricher_dir = Path(paths.enricher_dir)
    disease_subdir = step_cfg.get("disease_subdir") or disease_subdir
    out = []
    for i in range(len(resolved)):
        if i == control_index:
            continue
        label = resolved[i][0]
        input_file = str(mapper_dir / disease_subdir / label / csv_name)
        output_dir = str(enricher_dir / disease_subdir / label)
        out.append((EnricherStepPaths(input_file=input_file, output_dir=output_dir), label))
    return out


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

    # Apply project-level step config (enricher) if present
    step_cfg = project.get_step_config("enricher")
    if step_cfg:
        if step_cfg.get("input_file") is not None:
            input_file = step_cfg["input_file"]
        if step_cfg.get("input") is not None:
            input_file = step_cfg["input"]
        if step_cfg.get("output_dir") is not None:
            output_dir = step_cfg["output_dir"]
        if step_cfg.get("outdir") is not None:
            output_dir = step_cfg["outdir"]

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
