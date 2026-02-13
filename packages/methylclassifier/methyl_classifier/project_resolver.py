"""
Resolve MethylClassifier config from a pipeline project config (Pydantic only).
Supports binary (centroid1/centroid2) and N-group multiclass (centroid_dirs + multiclass_class_names).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from methyl_utils import load_project

from .models.config_schema import ClassificationConfig


def build_multiclass_config_from_project(
    project_path: Union[str, Path],
    dmps_csv: Optional[Union[str, Path]] = None,
    output_model: Optional[Union[str, Path]] = None,
    weights_column: Optional[str] = "importance",
    detection_dmps_glob: str = "dmps-*.csv",
) -> Dict[str, Any]:
    """
    Build a multiclass model config dict from a project (for use with build_multiclass_model).

    Uses the project's resolved groups (centroid_dirs + labels). If dmps_csv is not given,
    looks under the project's detection_dir for a DMP CSV (first file matching detection_dmps_glob).
    For N-class detection you typically run MethylDetector one-vs-rest or merge pairwise DMPs
    and place the merged CSV in detection_dir, or pass dmps_csv explicitly.

    Returns:
        Config dict with keys: dmps_csv, output_model, weights_column, classes (list of {name, centroid_dir}).
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    resolved = project.get_resolved_groups()
    if len(resolved) < 2:
        raise ValueError("Project must have at least 2 groups for multiclass")
    centroid_dirs = paths.centroid_dirs or [paths.centroid1_dir, paths.centroid2_dir]
    if len(centroid_dirs) != len(resolved):
        centroid_dirs = [f"{paths.output_base}/centroids/{label}" for label, _ in resolved]

    if dmps_csv is None:
        det_dir = Path(paths.detection_dir)
        if det_dir.exists():
            candidates = sorted(det_dir.glob(detection_dmps_glob))
            if candidates:
                dmps_csv = str(candidates[0])
            else:
                dmps_csv = str(det_dir / "dmps-all-biological.csv")
        else:
            dmps_csv = str(Path(paths.detection_dir) / "dmps-all-biological.csv")
    else:
        dmps_csv = str(Path(dmps_csv).resolve())

    if output_model is None:
        output_model = str(Path(paths.classifier_dir) / "multiclass-classifier.pkl")
    else:
        output_model = str(Path(output_model).resolve())

    classes: List[Dict[str, str]] = []
    for (label, _), cdir in zip(resolved, centroid_dirs):
        classes.append({"name": label, "centroid_dir": str(Path(cdir).resolve())})

    return {
        "dmps_csv": dmps_csv,
        "output_model": output_model,
        "weights_column": weights_column,
        "min_sample_coverage": 10,
        "coverage_weighting": True,
        "classes": classes,
    }


def resolve_classifier_config(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
    output_filename: str = "classification_results.csv",
) -> ClassificationConfig:
    """
    Build ClassificationConfig from a project config and optional step overrides.

    Model directory is set to the project's detection_dir (where MethylDetector
    writes trained classifiers). Centroid dirs and path_remap come from the project;
    output goes to classifier_dir.
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    resolved = project.get_resolved_groups()

    base = {
        "model_dir": paths.detection_dir,
        "centroid1_dir": paths.centroid1_dir,
        "centroid2_dir": paths.centroid2_dir,
        "output_path": str(Path(paths.classifier_dir) / output_filename),
    }
    if paths.centroid_dirs and len(paths.centroid_dirs) > 2:
        base["centroid_dirs"] = list(paths.centroid_dirs)
        base["multiclass_class_names"] = [resolved[i][0] for i in range(len(resolved))]
    if project.path_remap:
        base["centroid_path_remap"] = project.path_remap

    # Apply project-level step config (classifier) if present
    step_cfg = project.get_step_config("classifier")
    if step_cfg:
        for k, v in step_cfg.items():
            base[k] = v

    if step_override_path is not None:
        override_path = Path(step_override_path)
        if override_path.exists():
            with open(override_path) as f:
                overrides = json.load(f)
            for k, v in overrides.items():
                base[k] = v

    return ClassificationConfig(**base)
