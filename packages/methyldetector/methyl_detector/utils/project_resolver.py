"""
Resolve MethylDetector config from a pipeline project config (Pydantic).
Uses centroid1_dir and centroid2_dir (first two groups). For N-group multi-class,
run detection one-vs-rest or pairwise and merge DMPs; then use the merged DMP CSV
with the classifier multiclass builder (see build_multiclass_config_from_project).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from methyl_utils import load_project, ProjectConfig

from ..models.config import MethylModelerConfig


def resolve_detector_config_per_cancer_group(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
    control_index: int = 0,
    disease_subdir: str = "cancer",
) -> List[Tuple[MethylModelerConfig, str]]:
    """
    Build one MethylModelerConfig per non-control group (e.g. per cancer group).
    Control group (default index 0, e.g. healthy) is centroid1; each other group
    is centroid2 with output_dir = {detection_dir}/{disease_subdir}/{group_label}.

    Returns:
        List of (config, group_label) for each disease/cancer group.
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    resolved = project.get_resolved_groups()
    if len(resolved) < 2:
        return []
    centroid_dirs = getattr(paths, "centroid_dirs", None) or [paths.centroid1_dir, paths.centroid2_dir]
    if len(centroid_dirs) != len(resolved):
        centroid_dirs = [f"{paths.output_base}/centroids/{label}" for label, _ in resolved]
    c1_dir = centroid_dirs[control_index]
    step_cfg = project.get_step_config("detection") or {}
    if step_override_path is not None:
        with open(step_override_path) as f:
            overrides = json.load(f)
        step_cfg = {**step_cfg, **overrides}

    out: List[Tuple[MethylModelerConfig, str]] = []
    for i in range(len(resolved)):
        if i == control_index:
            continue
        label = resolved[i][0]
        base: Dict[str, Any] = {
            "chromosome": project.chromosomes or ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
                "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "X", "Y"],
            "contexts": project.contexts or ["CG"],
            "centroid1_dir": c1_dir,
            "centroid2_dir": centroid_dirs[i],
            "output_dir": str(Path(paths.detection_dir) / disease_subdir / label),
        }
        if project.get_group_sample_paths(control_index):
            base["centroid1_validation_samples"] = project.get_group_sample_paths(control_index)
        if project.get_group_sample_paths(i):
            base["centroid2_validation_samples"] = project.get_group_sample_paths(i)
        for k, v in step_cfg.items():
            base[k] = v
        out.append((MethylModelerConfig.model_validate(base), label))
    return out


def resolve_detector_config(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
) -> MethylModelerConfig:
    """
    Build MethylModelerConfig from a project config and optional step overrides.
    Uses Pydantic throughout; returns MethylModelerConfig (not dict).
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()

    base: Dict[str, Any] = {
        "chromosome": project.chromosomes or ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
            "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "X", "Y"],
        "contexts": project.contexts or ["CG"],
        "centroid1_dir": paths.centroid1_dir,
        "centroid2_dir": paths.centroid2_dir,
        "output_dir": paths.detection_dir,
    }
    # Optional: use project group sample paths as validation samples (detector can use "use_metadata" instead)
    if project.get_group1_sample_paths():
        base["centroid1_validation_samples"] = project.get_group1_sample_paths()
    if project.get_group2_sample_paths():
        base["centroid2_validation_samples"] = project.get_group2_sample_paths()

    # Apply project-level step config (detection) if present
    step_cfg = project.get_step_config("detection")
    if step_cfg:
        for k, v in step_cfg.items():
            base[k] = v

    if step_override_path is not None:
        with open(step_override_path) as f:
            overrides = json.load(f)
        for k, v in overrides.items():
            base[k] = v

    return MethylModelerConfig.model_validate(base)
