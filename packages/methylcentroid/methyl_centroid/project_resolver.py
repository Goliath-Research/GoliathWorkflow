"""
Resolve MethylCentroid batch config from a pipeline project config (Pydantic).
"""

import json
from pathlib import Path
from typing import Optional, Union

from methyl_utils import load_project

from .config import BatchProcessingConfig, MethylCentroidConfig


def resolve_centroid_batch_config(
    project_path: Union[str, Path],
    group: str,
    step_override_path: Optional[Union[str, Path]] = None,
) -> BatchProcessingConfig:
    """
    Build BatchProcessingConfig for one group from a project config.
    group must be "group1" or "group2".
    Returns Pydantic BatchProcessingConfig.
    """
    if group not in ("group1", "group2"):
        raise ValueError("group must be 'group1' or 'group2'")
    project = load_project(project_path)
    paths = project.get_derived_paths()
    if group == "group1":
        g = project.group1
        output_dir = paths.centroid1_dir
        sample_paths = project.get_group1_sample_paths()
    else:
        g = project.group2
        output_dir = paths.centroid2_dir
        sample_paths = project.get_group2_sample_paths()

    base_config = MethylCentroidConfig(
        laboratory=project.project_name,
        disease="",
        group=g.label,
        batch=project.project_name,
        chrom=project.chromosomes[0] if project.chromosomes else "1",
        ctx=project.contexts[0] if project.contexts else "CG",
        output_dir=output_dir,
        add_samples=sample_paths,
        min_coverage=4,
        use_gpu=True,
    )
    batch = BatchProcessingConfig(
        chromosomes=project.chromosomes or ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
            "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "X", "Y"],
        contexts=project.contexts or ["CG"],
        base_config=base_config,
    )
    if step_override_path is not None:
        with open(step_override_path) as f:
            overrides = json.load(f)
        if "base_config" in overrides:
            base_data = batch.base_config.model_dump()
            for k, v in overrides["base_config"].items():
                base_data[k] = v
            batch = batch.model_copy(update={"base_config": MethylCentroidConfig(**base_data)})
        for key in ("chromosomes", "contexts", "parallel_combinations", "continue_on_error", "save_batch_summary"):
            if key in overrides:
                batch = batch.model_copy(update={key: overrides[key]})
    return batch
