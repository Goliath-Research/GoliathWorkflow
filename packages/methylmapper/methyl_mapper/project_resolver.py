"""
Resolve MethylMapper (bedtools) paths from a pipeline project config.
Uses Pydantic only; no raw dict configs.
"""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from methyl_utils import load_project


class MapperStepPaths(BaseModel):
    """Paths for the mapper step derived from a project (and optional overrides)."""

    csv_pattern: str = Field(
        ...,
        description="Glob pattern for DMP CSVs (e.g. detection_dir/dmps-*-3-optimized.csv)",
    )
    output_dir: str = Field(
        ...,
        description="Output directory for mapped results (mapper_dir)",
    )


def resolve_mapper_paths(
    project_path: Path,
    step_override_path: Optional[Path] = None,
    csv_filename_pattern: str = "*.csv",
) -> MapperStepPaths:
    """
    Build mapper step paths from a project config.

    Input CSVs are read from project's detection_dir; output goes to mapper_dir.
    Optional step_override_path JSON can override csv_pattern and/or output_dir.
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    csv_pattern = str(Path(paths.detection_dir) / csv_filename_pattern)
    output_dir = paths.mapper_dir

    def _resolve_csv_pattern(pattern: str) -> str:
        """If pattern is relative, resolve under detection_dir so CSVs are found in detection folder."""
        p = Path(pattern)
        if p.is_absolute():
            return pattern
        return str(Path(paths.detection_dir) / pattern)

    # Apply project-level step config (mapper) if present.
    # Prefer csv_filename_pattern (mask under detection_dir) over full csv_pattern path.
    step_cfg = project.get_step_config("mapper")
    if step_cfg:
        if step_cfg.get("csv_filename_pattern") is not None:
            csv_pattern = str(Path(paths.detection_dir) / step_cfg["csv_filename_pattern"])
        elif step_cfg.get("csv_pattern") is not None:
            csv_pattern = _resolve_csv_pattern(step_cfg["csv_pattern"])
        if step_cfg.get("output_dir") is not None:
            output_dir = step_cfg["output_dir"]

    overrides: dict = {}
    if step_override_path and step_override_path.exists():
        import json
        with open(step_override_path) as f:
            overrides = json.load(f)

    if overrides.get("csv_filename_pattern") is not None:
        csv_pattern = str(Path(paths.detection_dir) / overrides["csv_filename_pattern"])
    elif overrides.get("csv_pattern") is not None:
        csv_pattern = _resolve_csv_pattern(overrides["csv_pattern"])
    if overrides.get("output_dir") is not None:
        output_dir = overrides["output_dir"]

    return MapperStepPaths(csv_pattern=csv_pattern, output_dir=output_dir)
