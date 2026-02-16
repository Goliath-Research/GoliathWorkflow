"""
Resolve MethylMapper (bedtools) paths from a pipeline project config.
Uses the same detection layout as MethylDetector/MethylClassifier: when the project
has multiple groups, detection outputs live under detection/{disease_subdir}/{label}
(e.g. detection/cancer/pca1, detection/cancer/pca2). The resolver can return either
a single pattern over all groups (detection/cancer/*/dmps-*.csv) or per-group
paths so each group's mapping is written to mapper/cancer/<label>.
"""

from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from methyl_utils import load_project

DISEASE_SUBDIR_DEFAULT = "cancer"


class MapperStepPaths(BaseModel):
    """Paths for the mapper step derived from a project (and optional overrides)."""

    csv_pattern: str = Field(
        ...,
        description="Glob pattern for DMP CSVs (e.g. detection_dir/cancer/*/dmps-*.csv)",
    )
    output_dir: str = Field(
        ...,
        description="Output directory for mapped results (mapper_dir)",
    )


def resolve_mapper_paths_per_cancer_group(
    project_path: Path,
    step_override_path: Optional[Path] = None,
    control_index: int = 0,
    disease_subdir: str = DISEASE_SUBDIR_DEFAULT,
    csv_filename_pattern: str = "dmps-*.csv",
) -> List[Tuple[MapperStepPaths, str]]:
    """
    Build one MapperStepPaths per comparison (control vs disease).
    When project uses control/disease + comparisons: one entry per get_comparisons().
    Otherwise: one per non-control group (flat groups).

    Returns:
        List of (MapperStepPaths, comparison_label) for each comparison.
    """
    project = load_project(project_path)
    step_cfg = project.get_step_config("mapper") or {}
    if step_override_path and step_override_path.exists():
        import json
        with open(step_override_path) as f:
            overrides = json.load(f)
        step_cfg = {**step_cfg, **overrides}
    pattern = step_cfg.get("csv_filename_pattern") or step_cfg.get("csv_pattern") or csv_filename_pattern
    if "/" in pattern or "\\" in pattern:
        pattern = Path(pattern).name

    if getattr(project, "uses_control_disease", lambda: False)():
        out: List[Tuple[MapperStepPaths, str]] = []
        for spec in project.get_comparisons():
            comp_label = spec.comparison_label or spec.disease_group
            det_dir = project.get_detection_output_dir(comp_label)
            map_dir = project.get_mapper_output_dir(comp_label)
            group_csv = str(Path(det_dir) / pattern)
            out.append((MapperStepPaths(csv_pattern=group_csv, output_dir=map_dir), comp_label))
        return out

    paths = project.get_derived_paths()
    resolved = getattr(project, "get_resolved_groups", lambda: [])()
    if len(resolved) < 2:
        return []
    detection_dir = Path(paths.detection_dir)
    mapper_dir = Path(paths.mapper_dir)
    disease_subdir = step_cfg.get("disease_subdir") or disease_subdir
    out = []
    for i in range(len(resolved)):
        if i == control_index:
            continue
        label = resolved[i][0]
        group_csv = str(detection_dir / disease_subdir / label / pattern)
        group_out = str(mapper_dir / disease_subdir / label)
        out.append((MapperStepPaths(csv_pattern=group_csv, output_dir=group_out), label))
    return out


def resolve_mapper_paths(
    project_path: Path,
    step_override_path: Optional[Path] = None,
    csv_filename_pattern: str = "*.csv",
) -> MapperStepPaths:
    """
    Build mapper step paths from a project config.

    Input CSVs are read from the project's detection layout:
    - When the project has multiple groups (e.g. healthy, pca1, pca2, ...), detection
      is assumed to run per-cancer-group and outputs live in detection/{disease_subdir}/{label}.
      The CSV pattern is set to detection/{disease_subdir}/*/{filename_pattern} so all
      group dirs are searched (same layout as methyl-classifier / methyl-detector).
    - Otherwise the pattern is detection_dir/{filename_pattern}.

    Optional step_override_path JSON can override csv_pattern and/or output_dir.
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    detection_dir = Path(paths.detection_dir)
    output_dir = paths.mapper_dir
    disease_subdir = DISEASE_SUBDIR_DEFAULT

    resolved_groups = getattr(project, "get_resolved_groups", lambda: [])()
    use_per_group_layout = len(resolved_groups) >= 2

    def _resolve_csv_pattern(pattern: str, use_per_group: bool) -> str:
        """Resolve pattern: absolute unchanged; relative under detection_dir, optionally under detection/disease_subdir/*/."""
        p = Path(pattern)
        if p.is_absolute():
            return pattern
        if use_per_group:
            return str(detection_dir / disease_subdir / "*" / pattern)
        return str(detection_dir / pattern)

    csv_pattern = _resolve_csv_pattern(csv_filename_pattern, use_per_group_layout)

    step_cfg = project.get_step_config("mapper")
    if step_cfg:
        disease_subdir = step_cfg.get("disease_subdir") or disease_subdir
        if step_cfg.get("csv_filename_pattern") is not None:
            csv_pattern = _resolve_csv_pattern(step_cfg["csv_filename_pattern"], use_per_group_layout)
        elif step_cfg.get("csv_pattern") is not None:
            csv_pattern = _resolve_csv_pattern(step_cfg["csv_pattern"], use_per_group_layout)
        if step_cfg.get("output_dir") is not None:
            output_dir = step_cfg["output_dir"]

    overrides: dict = {}
    if step_override_path and step_override_path.exists():
        import json
        with open(step_override_path) as f:
            overrides = json.load(f)

    if overrides.get("disease_subdir") is not None:
        disease_subdir = overrides["disease_subdir"]
    if overrides.get("csv_filename_pattern") is not None:
        csv_pattern = _resolve_csv_pattern(overrides["csv_filename_pattern"], use_per_group_layout)
    elif overrides.get("csv_pattern") is not None:
        csv_pattern = _resolve_csv_pattern(overrides["csv_pattern"], use_per_group_layout)
    if overrides.get("output_dir") is not None:
        output_dir = overrides["output_dir"]

    return MapperStepPaths(csv_pattern=csv_pattern, output_dir=output_dir)
