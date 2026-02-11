"""
Resolve MethylClassifier config from a pipeline project config (Pydantic only).
"""

import json
from pathlib import Path
from typing import Optional, Union

from methyl_utils import load_project

from ..models.config_schema import ClassificationConfig


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

    base = {
        "model_dir": paths.detection_dir,
        "centroid1_dir": paths.centroid1_dir,
        "centroid2_dir": paths.centroid2_dir,
        "output_path": str(Path(paths.classifier_dir) / output_filename),
    }
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
