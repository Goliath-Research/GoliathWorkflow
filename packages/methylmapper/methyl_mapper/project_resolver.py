"""
Resolve MethylMapper paths from a project config.

The canonical detector layout is comparison-based:

    detections/<control_group>/<disease_group>/

This resolver mirrors that contract for both explicit control/disease projects
and legacy flat-group projects, so mapper outputs land under the matching
comparison directory:

    mapper/<control_group>/<disease_group>/

By default the mapper consumes the detector's biological-only CSV exports
(`dmps-*-biological-sorted.csv`). Callers may override the filename pattern via
step config or a step-override JSON.
"""

from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from methyl_utils import load_project

# MethylDetector exports: dmps-{chr}-biological-sorted.csv (biological filter only) and dmps-{chr}.csv (optimized subset).
# Default to biological-only so mapper maps all biologically significant DMPs, not every CSV in the detection dir.
DMP_CSV_PATTERN_BIOLOGICAL = "dmps-*-biological-sorted.csv"


def _resolve_detection_dir_with_case_fallback(project, control_group: str, disease_group: str) -> Path:
    """
    Resolve detection directory with backward-compatible case-insensitive fallback.

    Some existing runs were written with lower-cased comparison directories
    (e.g. `pca_pca1`) while newer project labels may be mixed-case
    (`PCa_PCa1`). Prefer the canonical path, but reuse an existing directory
    with matching case-folded name when present.
    """
    canonical = Path(project.get_detection_output_dir(control_group, disease_group))
    if canonical.exists():
        return canonical
    parent = canonical.parent
    token = canonical.name.casefold()
    if parent.exists():
        for child in parent.iterdir():
            if child.is_dir() and child.name.casefold() == token:
                return child
    lower = canonical.with_name(canonical.name.lower())
    if lower.exists():
        return lower
    return canonical


class MapperStepPaths(BaseModel):
    """Paths for the mapper step derived from a project (and optional overrides)."""

    csv_pattern: str = Field(
        ...,
        description="Glob pattern for detector CSVs, typically under detections/<control>/<disease>/",
    )
    output_dir: str = Field(
        ...,
        description="Output directory for mapped results (mapper_dir)",
    )


def resolve_mapper_paths_per_cancer_group(
    project_path: Path,
    step_override_path: Optional[Path] = None,
    control_index: int = 0,
    disease_subdir: str = "disease",  # deprecated compatibility argument; comparison layout is canonical
    csv_filename_pattern: str = DMP_CSV_PATTERN_BIOLOGICAL,
) -> List[Tuple[MapperStepPaths, str]]:
    """
    Build one MapperStepPaths per comparison (control vs disease).
    When project uses control/disease + comparisons: one entry per get_comparisons().
    Otherwise: one per non-control group (flat groups).

    `disease_subdir` is ignored for the canonical comparison layout and is only
    kept to avoid breaking older callers.
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
            det_dir = _resolve_detection_dir_with_case_fallback(
                project,
                control_group=spec.control_group,
                disease_group=spec.disease_group,
            )
            map_dir = project.get_mapper_output_dir(spec.control_group, spec.disease_group)
            group_csv = str(Path(det_dir) / pattern)
            out.append((MapperStepPaths(csv_pattern=group_csv, output_dir=map_dir), comp_label))
        return out

    resolved = getattr(project, "get_resolved_groups", lambda: [])()
    if len(resolved) < 2:
        return []
    control_label = resolved[control_index][0]
    out = []
    for i in range(len(resolved)):
        if i == control_index:
            continue
        label = resolved[i][0]
        group_csv = str(Path(project.get_detection_output_dir(control_label, label)) / pattern)
        group_out = project.get_mapper_output_dir(control_label, label)
        out.append((MapperStepPaths(csv_pattern=group_csv, output_dir=group_out), label))
    return out


def resolve_mapper_paths(
    project_path: Path,
    step_override_path: Optional[Path] = None,
    csv_filename_pattern: str = DMP_CSV_PATTERN_BIOLOGICAL,
) -> MapperStepPaths:
    """
    Build mapper step paths from a project config.

    Build a single mapper input glob and output directory from the project.

    When the project is comparison-driven, the returned glob points at
    `detections/*/*/<pattern>` so all comparison directories are included. For
    legacy flat-group projects, it points at `detections/<control_group>/*/<pattern>`.
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    detection_dir = Path(paths.detection_dir)
    output_dir = paths.mapper_dir

    resolved_groups = getattr(project, "get_resolved_groups", lambda: [])()
    use_comparison_layout = len(resolved_groups) >= 2

    def _resolve_csv_pattern(pattern: str, use_comparison_dirs: bool) -> str:
        """Resolve pattern under the canonical comparison directory structure."""
        p = Path(pattern)
        if p.is_absolute():
            return pattern
        if use_comparison_dirs:
            if getattr(project, "uses_control_disease", lambda: False)():
                return str(detection_dir / "*" / "*" / pattern)
            control_label = resolved_groups[0][0]
            return str(detection_dir / control_label / "*" / pattern)
        return str(detection_dir / pattern)

    csv_pattern = _resolve_csv_pattern(csv_filename_pattern, use_comparison_layout)

    step_cfg = project.get_step_config("mapper")
    if step_cfg:
        if step_cfg.get("csv_filename_pattern") is not None:
            csv_pattern = _resolve_csv_pattern(step_cfg["csv_filename_pattern"], use_comparison_layout)
        elif step_cfg.get("csv_pattern") is not None:
            csv_pattern = _resolve_csv_pattern(step_cfg["csv_pattern"], use_comparison_layout)
        if step_cfg.get("output_dir") is not None:
            output_dir = step_cfg["output_dir"]

    overrides: dict = {}
    if step_override_path and step_override_path.exists():
        import json
        with open(step_override_path) as f:
            overrides = json.load(f)

    if overrides.get("csv_filename_pattern") is not None:
        csv_pattern = _resolve_csv_pattern(overrides["csv_filename_pattern"], use_comparison_layout)
    elif overrides.get("csv_pattern") is not None:
        csv_pattern = _resolve_csv_pattern(overrides["csv_pattern"], use_comparison_layout)
    if overrides.get("output_dir") is not None:
        output_dir = overrides["output_dir"]

    return MapperStepPaths(csv_pattern=csv_pattern, output_dir=output_dir)
