"""
Resolve MethylCentroid batch config from a pipeline project config (Pydantic).
Supports two-group (group1/group2) and N-group projects.
When a group has subcluster (and persist_centroids), runs MethylCluster first then
MethylCentroid once per discovered cluster (Option C: centroid step drives clustering).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from methyl_utils import load_project

from .config import BatchProcessingConfig, MethylCentroidConfig

logger = logging.getLogger(__name__)

CLUSTER_MANIFEST_FILENAME = "manifest.json"


def _get_group_config_for_label(project: Any, side: str, label: str) -> Optional[Any]:
    """Return the GroupConfig for (side, label) if project uses control/disease; else None."""
    if not project.uses_control_disease():
        return None
    if side == "control" and project.control:
        for g in project.control.groups:
            if g.label == label:
                return g
    if side == "disease" and project.disease:
        for g in project.disease.groups:
            if g.label == label:
                return g
    return None


def _run_cluster_then_centroids_per_cluster(
    project_path: Union[str, Path],
    side: str,
    group_label: str,
    step_override_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Run MethylCluster for the group, then MethylCentroid once per derived cluster.
    Writes centroids to get_centroid_dir(side, derived_label) for each derived_label.
    """
    from .cli import run_batch_processing

    project = load_project(project_path)
    clustering_dir = Path(project.get_clustering_output_dir(side, group_label))
    manifest_path = clustering_dir / CLUSTER_MANIFEST_FILENAME

    if not manifest_path.exists():
        logger.info("Running MethylCluster for group %s (manifest not found)", group_label)
        try:
            from methyl_cluster.project_resolver import (
                resolve_cluster_config_for_group,
                write_clustering_manifest,
            )
            from methyl_cluster.cluster import MethylCluster
        except ImportError as err:
            raise RuntimeError(
                "Subcluster group requires methyl_cluster. Install it or run clustering first: "
                "python -m methyl_cluster.cli --project <project> --group " + group_label
            ) from err
        config, _ = resolve_cluster_config_for_group(project_path, group_label, step_override)
        cluster = MethylCluster(config)
        results = cluster.run()
        write_clustering_manifest(config.output_dir, group_label, results, side)

    with open(manifest_path) as f:
        manifest = json.load(f)
    derived_labels: List[str] = manifest.get("derived_labels", [])
    groups: Dict[str, List[str]] = manifest.get("groups", {})
    if not derived_labels or not groups:
        logger.warning("Empty manifest at %s; skipping centroid build for %s", manifest_path, group_label)
        return

    chrom = project.chromosomes[0] if project.chromosomes else "1"
    ctx = project.contexts[0] if project.contexts else "CG"
    chromosomes = project.chromosomes or ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
        "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "X", "Y"]
    contexts = project.contexts or ["CG"]
    step_cfg = project.get_step_config("centroid") or {}
    if step_override_path is not None:
        with open(step_override_path) as f:
            step_cfg = {**step_cfg, **json.load(f)}

    for derived_label in derived_labels:
        sample_paths = groups.get(derived_label)
        if not sample_paths:
            continue
        output_dir = project.get_centroid_dir(side, derived_label)
        base_config = MethylCentroidConfig(
            laboratory=project.project_name,
            disease="",
            group=derived_label,
            batch=project.project_name,
            chrom=chrom,
            ctx=ctx,
            output_dir=output_dir,
            add_samples=sample_paths,
            min_coverage=step_cfg.get("base_config", {}).get("min_coverage", 4),
            use_gpu=step_cfg.get("base_config", {}).get("use_gpu", True),
        )
        batch = BatchProcessingConfig(
            chromosomes=chromosomes,
            contexts=contexts,
            base_config=base_config,
        )
        if "base_config" in step_cfg:
            for k, v in step_cfg["base_config"].items():
                if k != "output_dir" and hasattr(batch.base_config, k):
                    setattr(batch.base_config, k, v)
        run_batch_processing(batch)


def run_centroids_for_all_groups(
    project_path: Union[str, Path],
    step_override_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Run MethylCentroid batch for every resolved group. For groups with subcluster and
    persist_centroids, runs MethylCluster first then one centroid per derived cluster.
    """
    from .cli import run_batch_processing

    project = load_project(project_path)
    with_side: List[Tuple[str, List[str], str]] = project._get_resolved_groups_with_side()

    for i, (label, paths, side) in enumerate(with_side):
        group_config = _get_group_config_for_label(project, side, label)
        if (
            group_config
            and group_config.subcluster is not None
            and group_config.subcluster.enabled
            and group_config.subcluster.persist_centroids
        ):
            _run_cluster_then_centroids_per_cluster(
                project_path, side, label, step_override_path
            )
        else:
            batch = resolve_centroid_batch_config(project_path, i, step_override_path)
            run_batch_processing(batch)


def run_centroid_for_one_group(
    project_path: Union[str, Path],
    group: Union[str, int],
    step_override_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Run MethylCentroid for a single group (by index or 'group1'/'group2').
    If the group has subcluster + persist_centroids, runs MethylCluster then centroid per cluster.
    """
    from .cli import run_batch_processing

    project = load_project(project_path)
    if not isinstance(group, int) or not project.uses_control_disease():
        batch = resolve_centroid_batch_config(project_path, group, step_override_path)
        run_batch_processing(batch)
        return
    with_side = project._get_resolved_groups_with_side()
    if group < 0 or group >= len(with_side):
        batch = resolve_centroid_batch_config(project_path, group, step_override_path)
        run_batch_processing(batch)
        return
    label, _paths, side = with_side[group]
    group_config = _get_group_config_for_label(project, side, label)
    if (
        group_config
        and group_config.subcluster is not None
        and group_config.subcluster.enabled
        and group_config.subcluster.persist_centroids
    ):
        _run_cluster_then_centroids_per_cluster(
            project_path, side, label, step_override_path
        )
    else:
        batch = resolve_centroid_batch_config(project_path, group, step_override_path)
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
        if group < len(centroid_dirs):
            output_dir = centroid_dirs[group]
        else:
            side = "control" if group == 0 else "disease"
            output_dir = project.get_centroid_dir(side, label)
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
