"""
Resolve MethylCentroid batch config from a pipeline project config (Pydantic).
Supports two-group (group1/group2) and N-group projects.
When a group has level_labels_path (CSV mapping sample_path -> level), that group
is expanded into one centroid dir per level (disease levels or health levels).
"""

import json
from pathlib import Path
from typing import Optional, Union

from methyl_utils import load_project

from .config import BatchProcessingConfig, MethylCentroidConfig


def run_centroids_for_all_groups(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Run MethylCentroid batch for every resolved group (e.g. healthy_level1, healthy_level2,
    pca_early, pca_medium, pca_late). Use for N-group projects or when groups use level_labels_path.
    """
    from .cli import run_batch_processing
    project = load_project(project_path)
    resolved = project.get_resolved_groups()
    for i in range(len(resolved)):
        batch = resolve_centroid_batch_config(project_path, i, step_override_path)
        run_batch_processing(batch)


def resolve_centroid_batch_config(
    project_path: Union[str, Path],
    group: Union[str, int],
    step_override_path: Optional[Union[str, Path]] = None,
) -> BatchProcessingConfig:
    """
    Build BatchProcessingConfig for one group from a project config.
    group may be "group1", "group2", or an integer index 0, 1, ... for N-group projects.
    Returns Pydantic BatchProcessingConfig.
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    resolved = project.get_resolved_groups()

    if isinstance(group, int):
        if group < 0 or group >= len(resolved):
            raise ValueError(f"group index {group} out of range (have {len(resolved)} groups)")
        label = resolved[group][0]
        sample_paths = list(resolved[group][1])
        centroid_dirs = paths.centroid_dirs or [paths.centroid1_dir, paths.centroid2_dir]
        output_dir = centroid_dirs[group] if group < len(centroid_dirs) else f"{paths.output_base}/centroids/{label}"
    elif group == "group1":
        label = resolved[0][0]
        sample_paths = list(resolved[0][1])
        output_dir = paths.centroid1_dir
    elif group == "group2":
        if len(resolved) < 2:
            raise ValueError("project has only one group; use group1 or index 0")
        label = resolved[1][0]
        sample_paths = list(resolved[1][1])
        output_dir = paths.centroid2_dir
    else:
        raise ValueError("group must be 'group1', 'group2', or an integer index")

    base_config = MethylCentroidConfig(
        laboratory=project.project_name,
        disease="",
        group=label,
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
    # Apply project-level step config (centroid) if present (never override output_dir)
    step_cfg = project.get_step_config("centroid")
    if step_cfg:
        if "base_config" in step_cfg:
            base_data = batch.base_config.model_dump()
            for k, v in step_cfg["base_config"].items():
                if k != "output_dir":  # keep canonical path from get_derived_paths()
                    base_data[k] = v
            batch = batch.model_copy(update={"base_config": MethylCentroidConfig(**base_data)})
        for key in ("chromosomes", "contexts", "parallel_combinations", "continue_on_error", "save_batch_summary"):
            if key in step_cfg:
                batch = batch.model_copy(update={key: step_cfg[key]})
    if step_override_path is not None:
        with open(step_override_path) as f:
            overrides = json.load(f)
        if "base_config" in overrides:
            base_data = batch.base_config.model_dump()
            for k, v in overrides["base_config"].items():
                if k != "output_dir":
                    base_data[k] = v
            batch = batch.model_copy(update={"base_config": MethylCentroidConfig(**base_data)})
        for key in ("chromosomes", "contexts", "parallel_combinations", "continue_on_error", "save_batch_summary"):
            if key in overrides:
                batch = batch.model_copy(update={key: overrides[key]})
    # Ensure output_dir is always the derived path (output_base/project_name/centroids/...)
    if isinstance(group, int):
        canonical_output = paths.centroid_dirs[group] if (paths.centroid_dirs and group < len(paths.centroid_dirs)) else output_dir
    else:
        canonical_output = paths.centroid1_dir if group == "group1" else paths.centroid2_dir
    batch = batch.model_copy(
        update={"base_config": batch.base_config.model_copy(update={"output_dir": canonical_output})}
    )
    return batch
