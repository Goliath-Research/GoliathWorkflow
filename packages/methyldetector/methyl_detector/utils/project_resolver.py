"""
Resolve MethylDetector config from a pipeline project config (Pydantic).
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from methyl_utils import load_project, ProjectConfig

from ..models.config import MethylModelerConfig


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

    if step_override_path is not None:
        with open(step_override_path) as f:
            overrides = json.load(f)
        for k, v in overrides.items():
            base[k] = v

    return MethylModelerConfig.model_validate(base)
