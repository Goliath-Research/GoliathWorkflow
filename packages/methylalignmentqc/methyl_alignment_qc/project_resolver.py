"""
Resolve MethylAlignmentQC config from a pipeline project config (Pydantic).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from methyl_utils import load_project

from .models.config import AlignmentQCConfig


def resolve_alignment_qc_config(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
) -> AlignmentQCConfig:
    """
    Build AlignmentQCConfig from a project config and optional step overrides.

    Sample paths are concatenated from group1 and group2 (or restricted by
    step_config "groups"). Output directory is paths.alignment_qc_dir.
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()

    # Default: all samples from both groups
    sample_paths: List[str] = []
    step_cfg = project.get_step_config("alignment_qc")
    groups = step_cfg.get("groups") if step_cfg else None
    if groups is not None:
        for g in groups:
            if g == "group1":
                sample_paths.extend(project.get_group1_sample_paths())
            elif g == "group2":
                sample_paths.extend(project.get_group2_sample_paths())
    else:
        sample_paths = project.get_group1_sample_paths() + project.get_group2_sample_paths()

    base: Dict[str, Any] = {
        "sample_paths": sample_paths,
        "output_dir": paths.alignment_qc_dir,
        "validate_schema": True,
    }
    if step_cfg:
        for key in ("sample_paths", "output_dir", "validate_schema"):
            if key in step_cfg:
                base[key] = step_cfg[key]

    if step_override_path is not None:
        path = Path(step_override_path)
        if path.exists():
            with open(path) as f:
                overrides = json.load(f)
            for k, v in overrides.items():
                base[k] = v

    return AlignmentQCConfig.model_validate(base)
