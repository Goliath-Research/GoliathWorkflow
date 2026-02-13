"""
Health level discovery: run MethylCluster on a cohort (e.g. healthy samples),
write assignments CSV, then build one MethylCentroid dir per cluster.

Use this to discover heterogeneous "levels of health" without prior labels.
Output centroid dirs can be used as N groups in the pipeline (e.g. healthy_level1, healthy_level2).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .pipeline_config import load_project


def run_health_discovery(
    project_path: Union[str, Path],
    chrom: Optional[str] = None,
    ctx: Optional[str] = None,
    cluster_output_dir: Optional[Union[str, Path]] = None,
    centroid_output_base: Optional[Union[str, Path]] = None,
    label_prefix: str = "healthy_level",
    force_k: Optional[int] = None,
    clustering_method: str = "centroid",
    run_centroid_step: bool = True,
    use_group: str = "group1",
) -> Tuple[Dict[str, Any], Path]:
    """
    Run clustering on the specified group's samples, write assignments CSV,
    and optionally build one MethylCentroid dir per cluster.

    Args:
        project_path: Path to project config JSON (must have group1/group2 or groups).
        chrom: Chromosome for clustering (default: first from project).
        ctx: Context for clustering (default: first from project, e.g. CG).
        cluster_output_dir: Where to write cluster JSON and assignments CSV.
            Default: {project_root}/health_discovery.
        centroid_output_base: Base dir for centroid outputs (one subdir per cluster).
            Default: {project_root}/centroids.
        label_prefix: Prefix for cluster labels (e.g. healthy_level -> healthy_level1, healthy_level2).
        force_k: If set, force this many clusters (centroid/hierarchical methods).
        clustering_method: One of centroid, hierarchical, hdbscan.
        run_centroid_step: If True, run MethylCentroid for each cluster after clustering.
        use_group: Which group to use ('group1' or 'group2'), or group index as string ('0', '1').

    Returns:
        (results_dict from MethylCluster, path to assignments CSV).
    """
    project = load_project(project_path)
    paths = project.get_derived_paths()
    project_root = Path(paths.output_base)

    if use_group == "group1":
        sample_paths = project.get_group1_sample_paths()
    elif use_group == "group2":
        sample_paths = project.get_group2_sample_paths()
    elif use_group.isdigit():
        sample_paths = project.get_group_sample_paths(int(use_group))
    else:
        raise ValueError("use_group must be 'group1', 'group2', or a digit string (group index)")

    if len(sample_paths) < 2:
        raise ValueError(f"Need at least 2 samples for clustering; got {len(sample_paths)}")

    chrom = chrom or (project.chromosomes[0] if project.chromosomes else "1")
    ctx = ctx or (project.contexts[0] if project.contexts else "CG")
    cluster_output_dir = Path(cluster_output_dir or project_root / "health_discovery")
    cluster_output_dir.mkdir(parents=True, exist_ok=True)
    centroid_output_base = Path(centroid_output_base or project_root / "centroids")

    try:
        from methyl_cluster.config import MethylClusterConfig, ClusteringMethod
        from methyl_cluster.cluster import MethylCluster
    except ImportError as e:
        raise ImportError(
            "Health discovery requires methyl_cluster. Install it or set PYTHONPATH."
        ) from e

    cluster_cfg = MethylClusterConfig(
        samples=sample_paths,
        chrom=chrom,
        ctx=ctx,
        clustering_method=ClusteringMethod(clustering_method),
        output_dir=str(cluster_output_dir),
        cache_distance_matrix=True,
        use_gpu=True,
        force_k=force_k,
    )
    cluster = MethylCluster(cluster_cfg)
    results = cluster.run()

    # Build path -> cluster_id (exclude noise if present)
    sample_paths_list = results["sample_paths"]
    labels = results["labels"]
    path_to_cluster: Dict[str, str] = {}
    for path, label in zip(sample_paths_list, labels):
        if label == -1:
            path_to_cluster[path] = "noise"
        else:
            path_to_cluster[path] = f"cluster_{label}"

    # Write assignments CSV
    assignments_csv = cluster_output_dir / "assignments.csv"
    _write_assignments_csv(assignments_csv, path_to_cluster)

    if run_centroid_step:
        try:
            from methyl_centroid.config import BatchProcessingConfig, MethylCentroidConfig
            from methyl_centroid.cli import run_batch_processing
        except ImportError as e:
            raise ImportError(
                "Running centroid step requires methyl_centroid. Install it or set PYTHONPATH."
            ) from e

        chromosomes = project.chromosomes or [
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
            "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
            "21", "22", "X", "Y",
        ]
        contexts = project.contexts or ["CG"]

        cluster_assignments = results.get("cluster_assignments", {})
        for key, paths_in_cluster in cluster_assignments.items():
            if key == "noise" or not paths_in_cluster:
                continue
            # key is e.g. cluster_0, cluster_1
            idx = key.replace("cluster_", "") if key.startswith("cluster_") else key
            out_label = f"{label_prefix}{idx}"
            output_dir = centroid_output_base / out_label
            output_dir.mkdir(parents=True, exist_ok=True)

            base_config = MethylCentroidConfig(
                laboratory=project.project_name,
                disease="",
                group=out_label,
                batch=project.project_name,
                chrom=chromosomes[0],
                ctx=contexts[0],
                output_dir=str(output_dir),
                add_samples=paths_in_cluster,
                min_coverage=4,
                use_gpu=True,
            )
            batch = BatchProcessingConfig(
                chromosomes=chromosomes,
                contexts=contexts,
                base_config=base_config,
            )
            run_batch_processing(batch)

    return results, assignments_csv


def _write_assignments_csv(path: Path, path_to_cluster: Dict[str, str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        import csv
        w = csv.writer(f)
        w.writerow(["sample_path", "cluster_id"])
        for sample_path, cluster_id in sorted(path_to_cluster.items()):
            w.writerow([sample_path, cluster_id])


def main() -> None:
    """CLI for health level discovery."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Discover health levels: cluster a cohort (e.g. healthy), write assignments CSV, build one centroid dir per cluster.",
    )
    parser.add_argument("project", type=Path, help="Path to project config JSON")
    parser.add_argument("--chrom", default=None, help="Chromosome for clustering (default: first from project)")
    parser.add_argument("--ctx", default=None, help="Context for clustering (default: first from project)")
    parser.add_argument("--cluster-output-dir", type=Path, default=None, help="Output dir for cluster JSON and assignments CSV")
    parser.add_argument("--centroid-output-base", type=Path, default=None, help="Base dir for centroid subdirs per cluster")
    parser.add_argument("--label-prefix", default="healthy_level", help="Prefix for cluster labels")
    parser.add_argument("--force-k", type=int, default=None, help="Force K clusters (centroid/hierarchical)")
    parser.add_argument("--clustering-method", default="centroid", choices=["centroid", "hierarchical", "hdbscan"])
    parser.add_argument("--no-centroid", action="store_true", help="Only run clustering; do not build centroid dirs")
    parser.add_argument("--group", default="group1", help="Group to use: group1, group2, or 0-based index (e.g. 0)")
    args = parser.parse_args()
    run_health_discovery(
        args.project,
        chrom=args.chrom,
        ctx=args.ctx,
        cluster_output_dir=args.cluster_output_dir,
        centroid_output_base=args.centroid_output_base,
        label_prefix=args.label_prefix,
        force_k=args.force_k,
        clustering_method=args.clustering_method,
        run_centroid_step=not args.no_centroid,
        use_group=args.group,
    )
    print(f"Assignments CSV written. Centroid dirs built under centroid-output-base (unless --no-centroid).")


if __name__ == "__main__":
    main()
