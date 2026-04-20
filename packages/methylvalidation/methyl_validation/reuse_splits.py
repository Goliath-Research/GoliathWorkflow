"""
Load train/validation partitions from existing Monte Carlo ``run_XXXX`` directories.

Used to reuse the same stratified splits as a prior stability / default MC run when evaluating
models or post-model metrics, avoiding redundant split RNG and ensuring aligned partitions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .project_gen import _safe_cohort_filename_label
from .split import load_and_resolve_sample_paths, stratified_split, stratified_split_multiclass


def _resolved_set(paths: List[str]) -> set[str]:
    return {str(Path(p).resolve()) for p in paths}


def _partition_matches_pool(train: List[str], val: List[str], pool: List[str]) -> bool:
    """Train and val must be non-empty, disjoint, and exactly partition ``pool``."""
    rt = _resolved_set(train)
    rv = _resolved_set(val)
    rp = _resolved_set(pool)
    if not rt or not rv:
        return False
    if rt & rv:
        return False
    return rt | rv == rp


def try_load_binary_split_from_run_dir(
    run_dir: Path,
    control_paths: List[str],
    disease_paths: List[str],
    samples_base_path: str,
) -> Optional[Tuple[List[str], List[str], List[str], List[str]]]:
    """
    Load binary train/val lists from ``train_control.csv`` / ``train_disease.csv`` /
    ``val_control.csv`` / ``val_disease.csv`` under ``run_dir``.

    Returns None if files are missing or assignments are incompatible with the current cohort pools.
    """
    tc_csv = run_dir / "train_control.csv"
    td_csv = run_dir / "train_disease.csv"
    vc_csv = run_dir / "val_control.csv"
    vd_csv = run_dir / "val_disease.csv"
    if not all(p.is_file() for p in (tc_csv, td_csv, vc_csv, vd_csv)):
        return None

    train_control = load_and_resolve_sample_paths(tc_csv, samples_base_path)
    train_disease = load_and_resolve_sample_paths(td_csv, samples_base_path)
    val_control = load_and_resolve_sample_paths(vc_csv, samples_base_path)
    val_disease = load_and_resolve_sample_paths(vd_csv, samples_base_path)

    if not _partition_matches_pool(train_control, val_control, control_paths):
        return None
    if not _partition_matches_pool(train_disease, val_disease, disease_paths):
        return None

    return train_control, train_disease, val_control, val_disease


def try_load_multiclass_split_from_run_dir(
    run_dir: Path,
    cohort_paths_list: List[Tuple[str, List[str]]],
    cohort_labels: List[str],
    samples_base_path: str,
) -> Optional[Tuple[Dict[str, List[str]], Dict[str, List[str]]]]:
    """
    Load per-label train/val from ``training_<label>.csv`` / ``testing_<label>.csv`` (safe filenames).
    """
    pool_by_label = dict(cohort_paths_list)
    train_m: Dict[str, List[str]] = {}
    val_m: Dict[str, List[str]] = {}
    for lbl in cohort_labels:
        if lbl not in pool_by_label:
            return None
        safe = _safe_cohort_filename_label(lbl)
        tr = run_dir / f"training_{safe}.csv"
        te = run_dir / f"testing_{safe}.csv"
        if not tr.is_file() or not te.is_file():
            return None
        train_m[lbl] = load_and_resolve_sample_paths(tr, samples_base_path)
        val_m[lbl] = load_and_resolve_sample_paths(te, samples_base_path)
        if not _partition_matches_pool(train_m[lbl], val_m[lbl], pool_by_label[lbl]):
            return None
    return train_m, val_m


def resolve_iteration_split(
    *,
    layout: str,
    iteration_index: int,
    split_source_root: Path,
    cohort_paths_list: List[Tuple[str, List[str]]],
    cohort_labels: List[str],
    control_paths: List[str],
    disease_paths: List[str],
    train_fraction: float,
    seed_i: Optional[int],
    samples_base_path: str,
) -> Tuple[object, str]:
    """
    Try ``split_source_root/run_{iteration+1:04d}/`` first; fall back to stratified split.

    Returns:
        (split_payload, source_tag) where ``source_tag`` is ``\"reused\"`` or ``\"generated\"``.

    ``split_payload`` is a 4-tuple for binary layout, or ``(train_m, val_m)`` dict pair for multiclass.
    """
    run_dir = split_source_root / f"run_{iteration_index + 1:04d}"
    if layout == "binary":
        loaded = try_load_binary_split_from_run_dir(
            run_dir, control_paths, disease_paths, samples_base_path
        )
        if loaded is not None:
            return loaded, "reused"
        return (
            stratified_split(
                control_paths,
                disease_paths,
                train_fraction,
                seed=seed_i,
            ),
            "generated",
        )

    loaded_m = try_load_multiclass_split_from_run_dir(
        run_dir, cohort_paths_list, cohort_labels, samples_base_path
    )
    if loaded_m is not None:
        return loaded_m, "reused"
    return (
        stratified_split_multiclass(
            cohort_paths_list,
            train_fraction,
            seed=seed_i,
        ),
        "generated",
    )


def write_split_reuse_summary(path: Path, payload: Dict[str, object]) -> Path:
    """Write ``split_reuse_summary.json`` under the given directory (or exact path)."""
    out = path if path.suffix == ".json" else path / "split_reuse_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out
