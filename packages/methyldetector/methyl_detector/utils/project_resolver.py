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
    Build one MethylModelerConfig per comparison (control vs disease pair).
    When project uses control/disease + comparisons: one config per comparison from get_comparisons().
    When project uses flat groups: one config per non-control group (control index 0 vs each other).

    Returns:
        List of (config, comparison_label) for each comparison.
    """
    project = load_project(project_path)
    step_cfg = project.get_step_config("detection") or {}
    if step_override_path is not None:
        with open(step_override_path) as f:
            overrides = json.load(f)
        step_cfg = {**step_cfg, **overrides}

    if getattr(project, "uses_control_disease", lambda: False)():
        comparisons = project.get_comparisons()
        out: List[Tuple[MethylModelerConfig, str]] = []
        for spec in comparisons:
            ctrl_label = spec.control_group
            dis_label = spec.disease_group
            comp_label = spec.comparison_label or spec.disease_group
            base: Dict[str, Any] = {
                "chromosome": project.chromosomes or ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
                    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "X", "Y"],
                "contexts": project.contexts or ["CG"],
                "centroid1_dir": project.get_centroid_dir("control", ctrl_label),
                "centroid2_dir": project.get_centroid_dir("disease", dis_label),
                "output_dir": project.get_detection_output_dir(ctrl_label, dis_label),
            }
            try:
                base["centroid1_validation_samples"] = project.get_group_sample_paths_by_label(ctrl_label)
            except ValueError:
                pass
            try:
                base["centroid2_validation_samples"] = project.get_group_sample_paths_by_label(dis_label)
            except ValueError:
                pass
            for k, v in step_cfg.items():
                base[k] = v
            out.append((MethylModelerConfig.model_validate(base), comp_label))
        return out

    paths = project.get_derived_paths()
    resolved = project.get_resolved_groups()
    if len(resolved) < 2:
        return []
    centroid_dirs = getattr(paths, "centroid_dirs", None) or [paths.centroid1_dir, paths.centroid2_dir]
    if len(centroid_dirs) != len(resolved):
        centroid_dirs = []
        for i, (label, _) in enumerate(resolved):
            side = "control" if i == control_index else "disease"
            centroid_dirs.append(project.get_centroid_dir(side, label))
    c1_dir = centroid_dirs[control_index]
    out = []
    for i in range(len(resolved)):
        if i == control_index:
            continue
        label = resolved[i][0]
        base = {
            "chromosome": project.chromosomes or ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
                "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "X", "Y"],
            "contexts": project.contexts or ["CG"],
            "centroid1_dir": c1_dir,
            "centroid2_dir": centroid_dirs[i],
            "output_dir": project.get_detection_output_dir(resolved[control_index][0], label),
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
    When project uses control/disease with a single comparison, output_dir is
    detection/<disease_label> (e.g. detection/cancer); otherwise detection/.
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()

    if getattr(project, "uses_control_disease", lambda: False)() and len(project.get_comparisons()) == 1:
        spec = project.get_comparisons()[0]
        output_dir = project.get_detection_output_dir(spec.control_group, spec.disease_group)
    else:
        output_dir = paths.detection_dir

    base: Dict[str, Any] = {
        "chromosome": project.chromosomes or ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
            "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "X", "Y"],
        "contexts": project.contexts or ["CG"],
        "centroid1_dir": paths.centroid1_dir,
        "centroid2_dir": paths.centroid2_dir,
        "output_dir": output_dir,
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
