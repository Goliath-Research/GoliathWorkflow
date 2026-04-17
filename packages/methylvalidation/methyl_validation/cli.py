"""
CLI for Monte Carlo validation runner.
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from methyl_utils import load_project

from .config import MonteCarloConfig, assert_production_model_build_allowed
from .predictor_policy import assert_validation_predictor_accuracy_mode
from .pipeline_runner import (
    run_post_model_validation_binary,
    run_post_model_validation_multiclass,
    run_pipeline_for_iteration,
    run_pipeline_for_iteration_multiclass,
    run_pipeline_for_model,
    run_predictor_only_binary,
    run_predictor_only_multiclass,
)
from .project_gen import (
    apply_frozen_pipeline_artifacts_to_run_project,
    generate_run_project,
    generate_run_project_hierarchical_multiclass,
    generate_run_project_multiclass,
    infer_monte_carlo_layout,
)
from .split import load_and_resolve_sample_paths, stratified_split, stratified_split_multiclass
from .validator_metrics import (
    build_metrics_table,
    compute_resource_summary,
    compute_summary,
    iteration_scalar_metrics_from_run_dir,
    metrics_schema_descriptor,
    write_all_metrics_csv,
    write_resource_summary_json,
    write_metrics_distribution_plotly,
    write_step_timings_csv,
    write_summary_json,
)
from .stability import run_stability_analysis, freeze_production_model, build_production_model
from .rollout import evaluate_dual_run, write_rollout_report


_RUN_ID_RE = re.compile(r"^run_(\d{4})$")


def _digest_sample_paths(paths: List[str]) -> str:
    h = hashlib.sha256()
    for p in sorted(str(x) for x in paths):
        h.update(p.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _write_baseline_manifest(
    *,
    output_root: Path,
    mode: str,
    config: MonteCarloConfig,
    layout: str,
    cohort_paths_list: List[Tuple[str, List[str]]],
) -> Path:
    """
    Write a deterministic run manifest describing split policy, seed policy, and
    metric schema. This is the baseline lock artifact for cross-phase comparisons.
    """
    payload: Dict[str, Any] = {
        "manifest_version": "probabilistic_v2_baseline_v1",
        "mode": str(mode),
        "layout": str(layout),
        "n_iterations": int(config.n_iterations),
        "train_fraction": float(config.train_fraction),
        "seed_policy": {
            "base_seed": int(config.seed) if config.seed is not None else None,
            "per_iteration_seed_rule": "seed_i = base_seed + iteration_index",
            "split_strategy": "stratified_per_cohort",
        },
        "cohorts": [
            {
                "label": str(label),
                "n_samples": int(len(paths)),
                "sample_digest_sha256": _digest_sample_paths(paths),
            }
            for label, paths in cohort_paths_list
        ],
        "metrics_schema": metrics_schema_descriptor(),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    out = output_root / "baseline_manifest.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out


def _format_duration(seconds: float) -> str:
    total = int(max(0, round(float(seconds))))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _estimate_iteration_eta(completed_iteration_seconds: List[float], remaining_iterations: int) -> str:
    if remaining_iterations <= 0:
        return "0s"
    if not completed_iteration_seconds:
        return "unknown"
    avg = sum(completed_iteration_seconds) / max(1, len(completed_iteration_seconds))
    return _format_duration(avg * remaining_iterations)


def _list_existing_run_numbers(monte_carlo_runs_root: Path) -> List[int]:
    nums: List[int] = []
    if not monte_carlo_runs_root.is_dir():
        return nums
    for p in sorted(monte_carlo_runs_root.iterdir()):
        if not p.is_dir():
            continue
        m = _RUN_ID_RE.match(p.name)
        if m:
            nums.append(int(m.group(1)))
    return nums


def _resolve_resume_start_iteration(
    resume_arg: Optional[int],
    *,
    n_iterations: int,
    existing_runs: List[int],
) -> int:
    """
    Resolve 0-based start iteration for resume mode.

    resume_arg semantics:
      - None: no resume (start at 0)
      - 0   : auto-resume (repeat last existing run, then continue)
      - N>0 : resume starting from run N (1-based; run N is repeated)
    """
    if resume_arg is None:
        return 0
    if resume_arg < 0:
        raise ValueError("--resume must be >= 1 when provided with a run number")
    if resume_arg == 0:
        if not existing_runs:
            return 0
        return max(0, max(existing_runs) - 1)
    if resume_arg > n_iterations:
        raise ValueError(f"--resume run must be <= n_iterations ({n_iterations}), got {resume_arg}")
    return resume_arg - 1


def _load_existing_step_timings(
    step_timings_csv: Path,
    *,
    keep_until_iteration_exclusive: int,
) -> List[Dict[str, Any]]:
    if not step_timings_csv.is_file():
        return []
    kept: List[Dict[str, Any]] = []
    with open(step_timings_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            run_id = str(row.get("run_id") or "")
            m = _RUN_ID_RE.match(run_id)
            if not m:
                continue
            run_num = int(m.group(1))
            if run_num >= keep_until_iteration_exclusive:
                continue
            parsed: Dict[str, Any] = dict(row)
            for key in ("duration_seconds", "max_rss_mb"):
                if key in parsed and parsed[key] not in (None, ""):
                    try:
                        parsed[key] = float(parsed[key])
                    except (TypeError, ValueError):
                        pass
            for key in ("return_code", "n_train_samples", "n_val_samples", "n_processed_samples"):
                if key in parsed and parsed[key] not in (None, ""):
                    try:
                        parsed[key] = int(float(parsed[key]))
                    except (TypeError, ValueError):
                        pass
            kept.append(parsed)
    return kept


def _write_detector_featurecuts_override(
    run_dir: Path,
    config: "MonteCarloConfig",
) -> Optional[Path]:
    """
    Optionally write detector step override JSON for stability/FeatureCuts runs.

    Returns override path when any override is active, otherwise None.
    """
    enable_featurecuts = bool(config.stability_featurecuts_enabled)
    target_ba = config.stability_target_balanced_accuracy
    min_selected_dmps = config.stability_min_selected_dmps
    if not enable_featurecuts and target_ba is None and min_selected_dmps is None:
        return None

    import json

    payload: Dict[str, Any] = {}
    if enable_featurecuts or target_ba is not None or min_selected_dmps is not None:
        payload["classifier_dmp_selection"] = "featurecuts_validation"
    if target_ba is not None:
        payload["target_balanced_accuracy"] = float(target_ba)
    if min_selected_dmps is not None:
        payload["min_selected_dmps"] = int(min_selected_dmps)
    if not payload:
        return None
    out = run_dir / "detector_step_override.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out


def _count_csv_data_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def _count_run_samples_from_existing_files(run_dir: Path) -> Tuple[int, int]:
    train_files = sorted(set(list(run_dir.glob("train_*.csv")) + list(run_dir.glob("training_*.csv"))))
    val_files = sorted(set(list(run_dir.glob("val_*.csv")) + list(run_dir.glob("testing_*.csv"))))
    n_train = sum(_count_csv_data_rows(p) for p in train_files)
    n_val = sum(_count_csv_data_rows(p) for p in val_files)
    return int(n_train), int(n_val)


def _infer_monte_carlo_cohorts_from_project(
    project_data: Dict[str, Any],
    project_path: Path,
) -> List[Dict[str, str]]:
    """
    Build MC cohorts from a project JSON using resolved leaf labels.

    For control/disease projects this yields:
      - control group labels (e.g. all)
      - disease leaf labels (e.g. pca_pca1, pca_pca2, ...)
    For flat groups it yields group labels as-is.
    """
    def _norm_csv_path(p: str) -> str:
        # Keep relative paths as authored in the project (typically relative to repo root),
        # only normalize explicit absolute paths.
        pp = Path(str(p))
        return str(pp) if pp.is_absolute() else str(p)

    cohorts: List[Dict[str, str]] = []

    # Flat multiclass template
    groups = project_data.get("groups")
    if isinstance(groups, list) and groups:
        for g in groups:
            if not isinstance(g, dict):
                continue
            label = str(g.get("label") or "").strip()
            paths = g.get("sample_paths") or []
            if label and isinstance(paths, list) and len(paths) > 0:
                cohorts.append({"label": label, "csv": _norm_csv_path(str(paths[0]))})
        return cohorts

    # control/disease template (accept plural keys used in many project JSONs)
    controls = project_data.get("controls") or project_data.get("control") or {}
    diseases = project_data.get("diseases") or project_data.get("disease") or {}

    ctrl_groups = controls.get("groups") if isinstance(controls, dict) else None
    if isinstance(ctrl_groups, list):
        for g in ctrl_groups:
            if not isinstance(g, dict):
                continue
            label = str(g.get("label") or "").strip()
            paths = g.get("sample_paths") or []
            if label and isinstance(paths, list) and len(paths) > 0:
                cohorts.append({"label": label, "csv": _norm_csv_path(str(paths[0]))})

    dis_groups = diseases.get("groups") if isinstance(diseases, dict) else None
    if isinstance(dis_groups, list):
        for g in dis_groups:
            if not isinstance(g, dict):
                continue
            parent = str(g.get("label") or "").strip()
            stages = g.get("stages")
            if isinstance(stages, list) and stages:
                for st in stages:
                    if not isinstance(st, dict):
                        continue
                    stage_label = str(st.get("label") or "").strip()
                    paths = st.get("sample_paths") or []
                    if parent and stage_label and isinstance(paths, list) and len(paths) > 0:
                        cohorts.append(
                            {"label": f"{parent}_{stage_label}", "csv": _norm_csv_path(str(paths[0]))}
                        )
            else:
                label = parent
                paths = g.get("sample_paths") or []
                if label and isinstance(paths, list) and len(paths) > 0:
                    cohorts.append({"label": label, "csv": _norm_csv_path(str(paths[0]))})

    return cohorts


def _write_model_mc_outputs(
    backend_root: Path,
    rows: List[Dict[str, Any]],
    all_timings: List[Dict[str, Any]],
) -> None:
    df = build_metrics_table(rows)
    write_all_metrics_csv(df, backend_root / "all_metrics.csv")
    summary = compute_summary(df)
    write_summary_json(summary, backend_root / "metrics_summary.json")
    if all_timings:
        write_step_timings_csv(all_timings, backend_root / "step_timings.csv")
        resource_summary = compute_resource_summary(all_timings)
        if resource_summary:
            write_resource_summary_json(resource_summary, backend_root / "resource_summary.json")
    write_metrics_distribution_plotly(df, backend_root / "metrics_distributions_plotly.html")


def _score_backend_from_outputs(
    backend_root: Path,
    metric: str,
    stat: str,
) -> float:
    import json

    summary_path = backend_root / "metrics_summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"Missing backend summary: {summary_path}")
    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)
    metric_node = summary.get(metric)
    if metric_node is None and isinstance(summary.get("metrics"), dict):
        metric_node = summary["metrics"].get(metric)
    if metric_node is None:
        raise ValueError(f"Metric {metric!r} not found in {summary_path}")
    metric_summary = metric_node
    if stat == "median":
        p50 = ((metric_summary.get("percentiles") or {}).get("p50"))
        if p50 is None:
            raise ValueError(f"Median (p50) missing for metric {metric!r} in {summary_path}")
        return float(p50)
    return float(metric_summary.get("mean"))


def _write_backend_ranking(
    model_mc_root: Path,
    backends: List[str],
    metric: str,
    stat: str,
) -> List[Dict[str, Any]]:
    import json

    rows: List[Dict[str, Any]] = []
    for backend in backends:
        backend_root = model_mc_root / backend
        score = _score_backend_from_outputs(backend_root, metric=metric, stat=stat)
        rows.append({"backend": backend, "metric": metric, "stat": stat, "score": float(score)})
    rows.sort(key=lambda r: r["score"], reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx

    ranking_csv = model_mc_root / "backend_ranking.csv"
    with open(ranking_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["rank", "backend", "metric", "stat", "score"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    ranking_json = model_mc_root / "backend_ranking.json"
    with open(ranking_json, "w", encoding="utf-8") as f:
        json.dump({"metric": metric, "stat": stat, "rows": rows}, f, indent=2)
    return rows


def _shared_run_metadata_from_step_timings(
    rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    meta: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        run_id = str(row.get("run_id") or "")
        if not run_id:
            continue
        run = meta.setdefault(run_id, {"detector_ok": False, "n_train_samples": None, "n_val_samples": None})
        return_code = row.get("return_code")
        if row.get("step_name") == "methyl-detector" and isinstance(return_code, (int, float)) and int(return_code) == 0:
            run["detector_ok"] = True
        if row.get("n_train_samples") is not None:
            run["n_train_samples"] = int(row["n_train_samples"])
        if row.get("n_val_samples") is not None:
            run["n_val_samples"] = int(row["n_val_samples"])
    return meta


def _build_model_mc_shared_runs(
    *,
    base_project_for_runs: Path,
    config: MonteCarloConfig,
    layout: str,
    cohort_paths_list: List[Tuple[str, List[str]]],
    cohort_labels: List[str],
    control_paths: List[str],
    disease_paths: List[str],
    shared_root: Path,
    resume_arg: Optional[int],
    per_cancer_group: bool,
) -> List[Dict[str, Any]]:
    shared_root.mkdir(parents=True, exist_ok=True)
    _write_baseline_manifest(
        output_root=shared_root,
        mode="model_mc_shared",
        config=config,
        layout=layout,
        cohort_paths_list=cohort_paths_list,
    )
    rows: List[Dict[str, Any]] = []
    all_timings: List[Dict[str, Any]] = []
    existing_runs = _list_existing_run_numbers(shared_root)
    start_iteration_idx = _resolve_resume_start_iteration(
        resume_arg,
        n_iterations=config.n_iterations,
        existing_runs=existing_runs,
    )
    existing_timings: List[Dict[str, Any]] = []
    if resume_arg is not None and start_iteration_idx > 0:
        existing_timings = _load_existing_step_timings(
            shared_root / "step_timings.csv",
            keep_until_iteration_exclusive=start_iteration_idx + 1,
        )
        all_timings.extend(existing_timings)
        existing_meta = _shared_run_metadata_from_step_timings(existing_timings)
        for prev_i in range(start_iteration_idx):
            prev_run_id = f"run_{prev_i + 1:04d}"
            prev_run_dir = shared_root / prev_run_id
            if not prev_run_dir.is_dir():
                continue
            run_meta = existing_meta.get(prev_run_id, {})
            if not bool(run_meta.get("detector_ok")):
                continue
            rows.append(
                {
                    "iteration": prev_i + 1,
                    "run_id": prev_run_id,
                    "run_dir": str(prev_run_dir),
                    "project_json": str(prev_run_dir / "project.json"),
                    "n_train_samples": run_meta.get("n_train_samples"),
                    "n_val_samples": run_meta.get("n_val_samples"),
                }
            )
    if resume_arg is not None:
        for n in existing_runs:
            if n >= (start_iteration_idx + 1):
                run_dir = shared_root / f"run_{n:04d}"
                if run_dir.is_dir():
                    shutil.rmtree(run_dir)
        resume_label = "auto" if resume_arg == 0 else str(resume_arg)
        print(
            f"Resuming model-mc shared runs (--resume {resume_label}): "
            f"starting at run_{start_iteration_idx + 1:04d} through run_{config.n_iterations:04d}",
            file=sys.stderr,
        )

    completed_iteration_seconds: List[float] = []
    for i in range(start_iteration_idx, config.n_iterations):
        iteration_t0 = time.perf_counter()
        run_id = f"run_{i + 1:04d}"
        run_dir = shared_root / run_id
        seed_i = (config.seed + i) if config.seed is not None else None
        train_m: Dict[str, List[str]] = {}
        val_m: Dict[str, List[str]] = {}
        try:
            if layout == "binary":
                train_control, train_disease, val_control, val_disease = stratified_split(
                    control_paths,
                    disease_paths,
                    config.train_fraction,
                    seed=seed_i,
                )
            else:
                train_m, val_m = stratified_split_multiclass(
                    cohort_paths_list,
                    config.train_fraction,
                    seed=seed_i,
                )
        except ValueError as e:
            print(f"[model-mc:shared] Warning: iteration {i + 1} skipped: {e}", file=sys.stderr)
            continue

        if layout == "binary":
            (
                project_path,
                _,
                _,
                _val_control_csv,
                _val_disease_csv,
                centroid_group1_override,
                centroid_group2_override,
            ) = generate_run_project(
                base_project_for_runs,
                run_dir,
                run_id,
                str(shared_root),
                train_control,
                train_disease,
                val_control,
                val_disease,
                config.samples_base_path,
            )
            n_train_samples = len(train_control) + len(train_disease)
            n_val_samples = len(val_control) + len(val_disease)
            ok_iter, errors_iter, timings_iter = run_pipeline_for_iteration(
                project_path,
                per_cancer_group=per_cancer_group,
                logs_dir=run_dir / "logs",
                progress_callback=None,
                centroid_step_overrides={
                    "group1": centroid_group1_override,
                    "group2": centroid_group2_override,
                },
                detector_step_override=None,
                skip_centroid=False,
                config=config,
            )
        else:
            if layout == "multiclass":
                project_path, _val_groups_json = generate_run_project_multiclass(
                    base_project_for_runs,
                    run_dir,
                    run_id,
                    str(shared_root),
                    train_m,
                    val_m,
                    cohort_labels,
                    config.samples_base_path,
                )
            else:
                project_path, _val_groups_json = generate_run_project_hierarchical_multiclass(
                    base_project_for_runs,
                    run_dir,
                    run_id,
                    str(shared_root),
                    train_m,
                    val_m,
                    cohort_labels,
                    config.samples_base_path,
                )
            n_train_samples = sum(len(train_m[k]) for k in cohort_labels)
            n_val_samples = sum(len(val_m[k]) for k in cohort_labels)
            ok_iter, errors_iter, timings_iter = run_pipeline_for_iteration_multiclass(
                project_path,
                per_cancer_group=per_cancer_group,
                logs_dir=run_dir / "logs",
                progress_callback=None,
                detector_step_override=None,
                skip_centroid=False,
                config=config,
            )

        for t in timings_iter:
            all_timings.append(
                {
                    **t,
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "n_train_samples": n_train_samples,
                    "n_val_samples": n_val_samples,
                    "model_backend": "shared",
                }
            )
        if not ok_iter:
            for msg in errors_iter:
                print(f"[model-mc:shared] Error [{run_id}]: {msg}", file=sys.stderr)
            if config.abort_on_step_failure:
                raise RuntimeError("[model-mc:shared] abort_on_step_failure=true and detector stage failed")
            continue

        rows.append(
            {
                "iteration": i + 1,
                "run_id": run_id,
                "run_dir": str(run_dir),
                "project_json": str(project_path),
                "n_train_samples": n_train_samples,
                "n_val_samples": n_val_samples,
            }
        )
        elapsed = time.perf_counter() - iteration_t0
        completed_iteration_seconds.append(elapsed)
        eta = _estimate_iteration_eta(completed_iteration_seconds, config.n_iterations - (i + 1))
        print(
            f"[model-mc:shared] Completed iteration {i + 1}/{config.n_iterations} ({run_id}) "
            f"in {_format_duration(elapsed)} (ETA {eta})",
            file=sys.stderr,
        )

    if not rows:
        raise RuntimeError("No successful model-mc shared iterations")
    write_step_timings_csv(all_timings, shared_root / "step_timings.csv")
    return rows


def _run_model_mc_backend_from_shared_runs(
    *,
    backend: str,
    config: MonteCarloConfig,
    layout: str,
    cohort_paths_list: List[Tuple[str, List[str]]],
    backend_root: Path,
    shared_root: Path,
    shared_rows: List[Dict[str, Any]],
    resume_arg: Optional[int],
    per_cancer_group: bool,
) -> None:
    backend_root.mkdir(parents=True, exist_ok=True)
    _write_baseline_manifest(
        output_root=backend_root,
        mode="model_mc",
        config=config,
        layout=layout,
        cohort_paths_list=cohort_paths_list,
    )
    rows: List[Dict[str, Any]] = []
    all_timings: List[Dict[str, Any]] = []
    existing_runs = _list_existing_run_numbers(backend_root)
    start_iteration_idx = _resolve_resume_start_iteration(
        resume_arg,
        n_iterations=config.n_iterations,
        existing_runs=existing_runs,
    )
    if resume_arg is not None and start_iteration_idx > 0:
        for prev_i in range(start_iteration_idx):
            prev_run_id = f"run_{prev_i + 1:04d}"
            prev_run_dir = backend_root / prev_run_id
            if not prev_run_dir.is_dir():
                continue
            prev_scalar = iteration_scalar_metrics_from_run_dir(prev_run_dir)
            if prev_scalar:
                rows.append(
                    {
                        "iteration": prev_i + 1,
                        "run_id": prev_run_id,
                        "run_dir": str(prev_run_dir),
                        "model_backend": backend,
                        **prev_scalar,
                    }
                )
        all_timings.extend(
            _load_existing_step_timings(
                backend_root / "step_timings.csv",
                keep_until_iteration_exclusive=start_iteration_idx + 1,
            )
        )
    if resume_arg is not None:
        for n in existing_runs:
            if n >= (start_iteration_idx + 1):
                run_dir = backend_root / f"run_{n:04d}"
                if run_dir.is_dir():
                    shutil.rmtree(run_dir)

    shared_timings = _load_existing_step_timings(
        shared_root / "step_timings.csv",
        keep_until_iteration_exclusive=config.n_iterations + 1,
    )
    shared_timings_by_run: Dict[str, List[Dict[str, Any]]] = {}
    for t in shared_timings:
        run_id = str(t.get("run_id") or "")
        if run_id:
            shared_timings_by_run.setdefault(run_id, []).append(t)

    completed_iteration_seconds: List[float] = []
    for row in sorted(shared_rows, key=lambda r: int(r["iteration"])):
        i = int(row["iteration"]) - 1
        if i < start_iteration_idx:
            continue
        iteration_t0 = time.perf_counter()
        run_id = str(row["run_id"])
        shared_run_dir = Path(str(row["run_dir"]))
        project_path = Path(str(row.get("project_json") or (shared_run_dir / "project.json")))
        if not project_path.is_file():
            raise FileNotFoundError(f"Shared project.json missing for {run_id}: {project_path}")
        backend_run_dir = backend_root / run_id
        backend_run_dir.mkdir(parents=True, exist_ok=True)

        if layout == "binary":
            run_project = load_project(project_path)
            comparisons = run_project.get_comparisons()
            if comparisons:
                spec = comparisons[0]
                predictor_output_dir = backend_run_dir / "predictors" / spec.control_group / spec.disease_group
            else:
                predictor_output_dir = backend_run_dir / "predictors"
        else:
            predictor_output_dir = backend_run_dir / "predictors"

        backend_config = config.model_copy(update={"model_backend": backend})
        if (
            backend in {"tabular_sklearn", "generative_hybrid"}
            and not backend_config.model_bundle_dir
        ):
            backend_config = backend_config.model_copy(
                update={"model_bundle_dir": str(backend_run_dir / "model_bundle")}
            )

        n_train_samples = row.get("n_train_samples")
        n_val_samples = row.get("n_val_samples")

        for t in shared_timings_by_run.get(run_id, []):
            all_timings.append(
                {
                    **t,
                    "run_id": run_id,
                    "model_backend": backend,
                }
            )

        ok_model, errors_model, timings_model = run_pipeline_for_model(
            project_json=project_path,
            logs_dir=backend_run_dir / "logs" / "model",
            predictor_output_dir=predictor_output_dir,
            per_cancer_group=per_cancer_group,
            config=backend_config,
        )
        for t in timings_model:
            all_timings.append(
                {
                    **t,
                    "run_id": run_id,
                    "run_dir": str(backend_run_dir),
                    "n_train_samples": n_train_samples,
                    "n_val_samples": n_val_samples,
                    "model_backend": backend,
                }
            )
        if not ok_model:
            for msg in errors_model:
                print(f"[model-mc:{backend}] Error [{run_id}]: {msg}", file=sys.stderr)
            if config.abort_on_step_failure:
                raise RuntimeError(f"[model-mc:{backend}] abort_on_step_failure=true and model stage failed")
            continue
        scalar = iteration_scalar_metrics_from_run_dir(backend_run_dir)
        rows.append({"iteration": i + 1, "run_id": run_id, "run_dir": str(backend_run_dir), "model_backend": backend, **scalar})
        elapsed = time.perf_counter() - iteration_t0
        completed_iteration_seconds.append(elapsed)
        eta = _estimate_iteration_eta(completed_iteration_seconds, config.n_iterations - (i + 1))
        print(
            f"[model-mc:{backend}] Completed iteration {i + 1}/{config.n_iterations} ({run_id}) "
            f"in {_format_duration(elapsed)} (ETA {eta})",
            file=sys.stderr,
        )

    if not rows:
        raise RuntimeError(f"No successful model-mc iterations for backend={backend}")
    _write_model_mc_outputs(backend_root=backend_root, rows=rows, all_timings=all_timings)


def _load_model_mc_shared_rows(
    *,
    shared_root: Path,
    n_iterations: int,
) -> List[Dict[str, Any]]:
    def _remap_shared_project_paths(project_json: Path, run_dir: Path) -> None:
        if not project_json.is_file():
            return
        try:
            payload = json.loads(project_json.read_text(encoding="utf-8"))
        except Exception:
            return
        changed = False
        if isinstance(payload, dict):
            new_output_base = str(run_dir.parent)
            if payload.get("output_base") != new_output_base:
                payload["output_base"] = new_output_base
                changed = True
        model_mc_root = run_dir.parent.parent
        run_id = run_dir.name
        target_prefix = str(run_dir)
        source_prefixes = [
            str(model_mc_root / backend / run_id)
            for backend in ("ecdf", "tabular_sklearn", "generative_hybrid", "shared")
        ]

        def _rewrite(value: Any) -> Any:
            nonlocal changed
            if isinstance(value, str):
                for src in source_prefixes:
                    if value == src or value.startswith(f"{src}/"):
                        mapped = f"{target_prefix}{value[len(src):]}"
                        if mapped != value:
                            changed = True
                        return mapped
                for backend in ("ecdf", "tabular_sklearn", "generative_hybrid", "shared"):
                    marker = f"/model_mc/{backend}/{run_id}"
                    idx = value.find(marker)
                    if idx >= 0:
                        mapped = f"{target_prefix}{value[idx + len(marker):]}"
                        if mapped != value:
                            changed = True
                        return mapped
                return value
            if isinstance(value, list):
                return [_rewrite(v) for v in value]
            if isinstance(value, dict):
                return {k: _rewrite(v) for k, v in value.items()}
            return value

        rewritten = _rewrite(payload)
        if changed:
            project_json.write_text(json.dumps(rewritten, indent=2), encoding="utf-8")

    run_numbers = [n for n in _list_existing_run_numbers(shared_root) if n <= n_iterations]
    if not run_numbers:
        raise RuntimeError(f"No shared runs found under {shared_root}")
    timings = _load_existing_step_timings(
        shared_root / "step_timings.csv",
        keep_until_iteration_exclusive=n_iterations + 1,
    )
    meta_by_run = _shared_run_metadata_from_step_timings(timings)
    rows: List[Dict[str, Any]] = []
    for run_number in run_numbers:
        run_id = f"run_{run_number:04d}"
        run_dir = shared_root / run_id
        project_json = run_dir / "project.json"
        _remap_shared_project_paths(project_json, run_dir)
        if not project_json.is_file():
            continue
        run_meta = meta_by_run.get(run_id, {})
        if timings and not bool(run_meta.get("detector_ok")):
            continue
        rows.append(
            {
                "iteration": run_number,
                "run_id": run_id,
                "run_dir": str(run_dir),
                "project_json": str(project_json),
                "n_train_samples": run_meta.get("n_train_samples"),
                "n_val_samples": run_meta.get("n_val_samples"),
            }
        )
    if not rows:
        raise RuntimeError(
            f"Shared runs under {shared_root} are missing usable project.json/detector outputs"
        )
    return rows


def _run_model_mc_backend(
    *,
    backend: str,
    base_project_for_runs: Path,
    config: MonteCarloConfig,
    layout: str,
    cohort_paths_list: List[Tuple[str, List[str]]],
    cohort_labels: List[str],
    control_paths: List[str],
    disease_paths: List[str],
    backend_root: Path,
    resume_arg: Optional[int],
    per_cancer_group: bool,
) -> None:
    backend_root.mkdir(parents=True, exist_ok=True)
    _write_baseline_manifest(
        output_root=backend_root,
        mode="model_mc",
        config=config,
        layout=layout,
        cohort_paths_list=cohort_paths_list,
    )
    rows: List[Dict[str, Any]] = []
    all_timings: List[Dict[str, Any]] = []

    existing_runs = _list_existing_run_numbers(backend_root)
    start_iteration_idx = _resolve_resume_start_iteration(
        resume_arg,
        n_iterations=config.n_iterations,
        existing_runs=existing_runs,
    )
    if resume_arg is not None and start_iteration_idx > 0:
        for prev_i in range(start_iteration_idx):
            prev_run_id = f"run_{prev_i + 1:04d}"
            prev_run_dir = backend_root / prev_run_id
            if not prev_run_dir.is_dir():
                continue
            prev_scalar = iteration_scalar_metrics_from_run_dir(prev_run_dir)
            if prev_scalar:
                rows.append(
                    {
                        "iteration": prev_i + 1,
                        "run_id": prev_run_id,
                        "run_dir": str(prev_run_dir),
                        "model_backend": backend,
                        **prev_scalar,
                    }
                )
        all_timings.extend(
            _load_existing_step_timings(
                backend_root / "step_timings.csv",
                keep_until_iteration_exclusive=start_iteration_idx + 1,
            )
        )
    if resume_arg is not None:
        for n in existing_runs:
            if n >= (start_iteration_idx + 1):
                run_dir = backend_root / f"run_{n:04d}"
                if run_dir.is_dir():
                    shutil.rmtree(run_dir)
    completed_iteration_seconds: List[float] = []

    for i in range(start_iteration_idx, config.n_iterations):
        iteration_t0 = time.perf_counter()
        run_id = f"run_{i + 1:04d}"
        run_dir = backend_root / run_id
        seed_i = (config.seed + i) if config.seed is not None else None
        train_m: Dict[str, List[str]] = {}
        val_m: Dict[str, List[str]] = {}
        try:
            if layout == "binary":
                train_control, train_disease, val_control, val_disease = stratified_split(
                    control_paths,
                    disease_paths,
                    config.train_fraction,
                    seed=seed_i,
                )
            else:
                train_m, val_m = stratified_split_multiclass(
                    cohort_paths_list,
                    config.train_fraction,
                    seed=seed_i,
                )
        except ValueError as e:
            print(f"[model-mc:{backend}] Warning: iteration {i + 1} skipped: {e}", file=sys.stderr)
            continue

        if layout == "binary":
            (
                project_path,
                _,
                _,
                _val_control_csv,
                _val_disease_csv,
                centroid_group1_override,
                centroid_group2_override,
            ) = generate_run_project(
                base_project_for_runs,
                run_dir,
                run_id,
                str(backend_root),
                train_control,
                train_disease,
                val_control,
                val_disease,
                config.samples_base_path,
            )
            run_project = load_project(project_path)
            comparisons = run_project.get_comparisons()
            if comparisons:
                spec = comparisons[0]
                predictor_output_dir = run_dir / "predictors" / spec.control_group / spec.disease_group
            else:
                predictor_output_dir = run_dir / "predictors"
            n_train_samples = len(train_control) + len(train_disease)
            n_val_samples = len(val_control) + len(val_disease)
            ok_iter, errors_iter, timings_iter = run_pipeline_for_iteration(
                project_path,
                per_cancer_group=per_cancer_group,
                logs_dir=run_dir / "logs",
                progress_callback=None,
                centroid_step_overrides={
                    "group1": centroid_group1_override,
                    "group2": centroid_group2_override,
                },
                detector_step_override=None,
                skip_centroid=False,
                config=config,
            )
        else:
            if layout == "multiclass":
                project_path, _val_groups_json = generate_run_project_multiclass(
                    base_project_for_runs,
                    run_dir,
                    run_id,
                    str(backend_root),
                    train_m,
                    val_m,
                    cohort_labels,
                    config.samples_base_path,
                )
            else:
                project_path, _val_groups_json = generate_run_project_hierarchical_multiclass(
                    base_project_for_runs,
                    run_dir,
                    run_id,
                    str(backend_root),
                    train_m,
                    val_m,
                    cohort_labels,
                    config.samples_base_path,
                )
            predictor_output_dir = run_dir / "predictors"
            n_train_samples = sum(len(train_m[k]) for k in cohort_labels)
            n_val_samples = sum(len(val_m[k]) for k in cohort_labels)
            ok_iter, errors_iter, timings_iter = run_pipeline_for_iteration_multiclass(
                project_path,
                per_cancer_group=per_cancer_group,
                logs_dir=run_dir / "logs",
                progress_callback=None,
                detector_step_override=None,
                skip_centroid=False,
                config=config,
            )

        for t in timings_iter:
            all_timings.append(
                {
                    **t,
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "n_train_samples": n_train_samples,
                    "n_val_samples": n_val_samples,
                    "model_backend": backend,
                }
            )
        if not ok_iter:
            for msg in errors_iter:
                print(f"[model-mc:{backend}] Error [{run_id}]: {msg}", file=sys.stderr)
            if config.abort_on_step_failure:
                raise RuntimeError(f"[model-mc:{backend}] abort_on_step_failure=true and detector stage failed")
            continue

        ok_model, errors_model, timings_model = run_pipeline_for_model(
            project_json=project_path,
            logs_dir=run_dir / "logs" / "model",
            predictor_output_dir=predictor_output_dir,
            per_cancer_group=per_cancer_group,
            config=config.model_copy(update={"model_backend": backend}),
        )
        for t in timings_model:
            all_timings.append(
                {
                    **t,
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "n_train_samples": n_train_samples,
                    "n_val_samples": n_val_samples,
                    "model_backend": backend,
                }
            )
        if not ok_model:
            for msg in errors_model:
                print(f"[model-mc:{backend}] Error [{run_id}]: {msg}", file=sys.stderr)
            if config.abort_on_step_failure:
                raise RuntimeError(f"[model-mc:{backend}] abort_on_step_failure=true and model stage failed")
            continue
        scalar = iteration_scalar_metrics_from_run_dir(run_dir)
        rows.append({"iteration": i + 1, "run_id": run_id, "run_dir": str(run_dir), "model_backend": backend, **scalar})
        elapsed = time.perf_counter() - iteration_t0
        completed_iteration_seconds.append(elapsed)
        eta = _estimate_iteration_eta(completed_iteration_seconds, config.n_iterations - (i + 1))
        print(
            f"[model-mc:{backend}] Completed iteration {i + 1}/{config.n_iterations} ({run_id}) "
            f"in {_format_duration(elapsed)} (ETA {eta})",
            file=sys.stderr,
        )

    if not rows:
        raise RuntimeError(f"No successful model-mc iterations for backend={backend}")
    _write_model_mc_outputs(backend_root=backend_root, rows=rows, all_timings=all_timings)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Monte Carlo validation: stratified train/val splits, methyl-centroid + methyl-detector per "
            "iteration; optional --predictor-only uses a frozen model. Supports binary and multiclass "
            "templates. Use --freeze then --model for mapper/enricher and classifier→predictor. "
            "Blind-only predictor configs are rejected."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        required=False,
        default=None,
        help="Path to Monte Carlo config JSON (alternative to --project).",
    )
    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        required=False,
        default=None,
        help="Path to pipeline project config JSON containing step_config.validation (alternative to --config).",
    )
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=None,
        metavar="N",
        help="Override n_iterations from config.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="S",
        help="Override seed from config.",
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        default=None,
        metavar="DIR",
        help="Override output_base from config.",
    )
    parser.add_argument(
        "--samples-base-path",
        type=Path,
        default=None,
        metavar="DIR",
        help="Override samples_base_path (and write it into production project.json for --freeze).",
    )
    parser.add_argument(
        "--path-remap",
        action="append",
        default=None,
        metavar="OLD=NEW",
        help=(
            "Prefix remap for path strings in the production project JSON (repeatable), e.g. samples_base_path. "
            "User cohort lists and MV training_*.csv use basenames; MV testing_*.csv uses absolute paths and is "
            "rewritten when referenced. Use --samples-base-path to set the sample root explicitly. "
            "Example: --path-remap /lambda/nfs/Work/prostate-cancer=/work/prostate-cancer"
        ),
    )
    parser.add_argument(
        "--stability",
        action="store_true",
        help="After main analysis, run stability on detector DMP exports from centroid+detector iterations (classifier/predictor via --model).",
    )
    parser.add_argument(
        "--stability-featurecuts",
        action="store_true",
        help="During MC stability runs, force detector classifier_dmp_selection=featurecuts_validation.",
    )
    parser.add_argument(
        "--stability-target-ba",
        type=float,
        default=None,
        metavar="BA",
        help="Optional detector target balanced accuracy for FeatureCuts (0..1).",
    )
    parser.add_argument(
        "--stability-min-selected-dmps",
        type=int,
        default=None,
        metavar="N",
        help="Optional lower bound for detector selected DMPs in FeatureCuts mode.",
    )
    parser.add_argument(
        "--resume",
        nargs="?",
        const=0,
        type=int,
        default=None,
        metavar="RUN",
        help=(
            "Resume interrupted MC runs. Without RUN, repeats last existing run then continues "
            "to n_iterations. With RUN (1-based), restarts from run_00RUN and continues."
        ),
    )
    parser.add_argument(
        "--skip-centroid",
        action="store_true",
        help=(
            "Reuse existing per-run centroids and run detector only. Useful when tuning "
            "step_config.detection hyperparameters on already-generated MC runs."
        ),
    )
    parser.add_argument(
        "--skip-enricher",
        action="store_true",
        help="Skip methyl-enricher step (useful when Grok API calls are slow).",
    )
    parser.add_argument(
        "--freeze",
        action="store_true",
        help="Run production freeze: centroid→detector(fixed panel)→mapper→enricher; optional progression via step_config.progression.enabled (no classifier/predictor).",
    )
    parser.add_argument(
        "--model",
        action="store_true",
        help="Build production model after --freeze. ecdf backend: classifier→predictor; tabular/generative backends: bundle→train→predict (no detector, not Monte Carlo). Use --predictor-only for repeated predictor-only runs.",
    )
    parser.add_argument(
        "--model-mc",
        action="store_true",
        help=(
            "Run full Monte Carlo retrain+test model stage per split (centroid->detector->train->predict) "
            "for model backend selection. Outputs are isolated under monte_carlo_runs/model_mc/<backend>/."
        ),
    )
    parser.add_argument(
        "--model-mc-all",
        action="store_true",
        help="With --model-mc, run all backends (ecdf, tabular_sklearn, generative_hybrid).",
    )
    parser.add_argument(
        "--select-best-model",
        action="store_true",
        help=(
            "Select the best backend from model-mc summaries and train final production model on all data "
            "using that backend."
        ),
    )
    parser.add_argument(
        "--rollout-compare",
        action="store_true",
        help=(
            "Compare baseline vs candidate metrics_summary.json using rollout thresholds "
            "and write a go/no-go recommendation report."
        ),
    )
    parser.add_argument(
        "--baseline-summary",
        type=Path,
        default=None,
        metavar="FILE",
        help="Path to baseline metrics_summary.json for --rollout-compare.",
    )
    parser.add_argument(
        "--candidate-summary",
        type=Path,
        default=None,
        metavar="FILE",
        help="Path to candidate metrics_summary.json for --rollout-compare.",
    )
    parser.add_argument(
        "--rollout-report",
        type=Path,
        default=None,
        metavar="FILE",
        help="Optional output path for rollout report JSON (default: monte_carlo_runs/rollout_decision.json).",
    )
    parser.add_argument(
        "--selection-metric",
        type=str,
        default="balanced_accuracy",
        metavar="METRIC",
        help="Metric used to rank backends for --select-best-model (default: balanced_accuracy).",
    )
    parser.add_argument(
        "--selection-stat",
        choices=["mean", "median"],
        default="median",
        help="Statistic used to rank backends for --select-best-model (default: median).",
    )
    parser.add_argument(
        "--post-model-validation",
        action="store_true",
        help=(
            "Run Monte Carlo holdout evaluation using the frozen production model artifacts "
            "(no retraining) and export empirical metric distributions under "
            "monte_carlo_runs/post_model_validation."
        ),
    )
    parser.add_argument(
        "--model-backend",
        choices=["ecdf", "tabular_sklearn", "generative_hybrid"],
        default=None,
        help=(
            "Override validation.model_backend for --model, --model-mc, and --post-model-validation "
            "(default comes from step_config.validation.model_backend or ecdf)."
        ),
    )
    parser.add_argument(
        "--post-model-backend",
        choices=["ecdf", "tabular_sklearn", "generative_hybrid"],
        default=None,
        help=(
            "Alias for backend override used with --post-model-validation. "
            "When omitted, uses step_config.validation.model_backend."
        ),
    )
    parser.add_argument(
        "--covariates-path",
        type=Path,
        default=None,
        metavar="FILE",
        help="Optional covariates sidecar for tabular_sklearn or generative_hybrid backends (.h5 preferred; .csv accepted).",
    )
    parser.add_argument(
        "--tabular-max-dmps",
        type=int,
        default=None,
        metavar="N",
        help="For tabular backend: max DMP loci from bundle index.",
    )
    parser.add_argument(
        "--tabular-model-type",
        choices=["random_forest", "hist_gradient_boosting", "logistic_regression"],
        default=None,
        help="For tabular backend: sklearn estimator type.",
    )
    parser.add_argument(
        "--tabular-methods-json",
        type=str,
        default=None,
        metavar="JSON",
        help=(
            "For tabular backend: JSON array of nested method configs, e.g. "
            "[{\"method\":\"random_forest\",\"params\":{...}}, ...]."
        ),
    )
    parser.add_argument(
        "--generative-latent-dim",
        type=int,
        default=None,
        metavar="N",
        help="For generative_hybrid backend: latent dimensionality.",
    )
    parser.add_argument(
        "--generative-kl-weight",
        type=float,
        default=None,
        metavar="W",
        help="For generative_hybrid backend: KL-like regularization weight.",
    )
    parser.add_argument(
        "--generative-density-type",
        choices=["diag_gaussian"],
        default=None,
        help="For generative_hybrid backend: latent density type.",
    )
    parser.add_argument(
        "--generative-epochs",
        type=int,
        default=None,
        metavar="N",
        help="For generative_hybrid backend: number of training epochs.",
    )
    parser.add_argument(
        "--generative-batch-size",
        type=int,
        default=None,
        metavar="N",
        help="For generative_hybrid backend: batch size.",
    )
    parser.add_argument(
        "--generative-seed",
        type=int,
        default=None,
        metavar="S",
        help="For generative_hybrid backend: random seed.",
    )
    parser.add_argument(
        "--generative-calibrate",
        action="store_true",
        help="For generative_hybrid backend: enable calibration stage when available.",
    )
    parser.add_argument(
        "--no-generative-covariates-strict",
        action="store_true",
        help="For generative_hybrid backend: do not fail when covariate rows are missing for some samples.",
    )
    parser.add_argument(
        "--predictor-only",
        action="store_true",
        help="Each iteration runs only methyl-predictor on MC holdouts; use frozen_project_path or monte_carlo_runs/production/project.json.",
    )
    args = parser.parse_args()

    # Support both --config (dedicated MC config) and --project (project with step_config.validation)
    if args.project is not None:
        # Load project and extract validation settings from step_config.validation
        import json
        with open(args.project, encoding="utf-8") as f:
            project_data = json.load(f)

        if "step_config" in project_data and "validation" in project_data.get("step_config", {}):
            validation_settings = project_data["step_config"]["validation"]
            cohorts = _infer_monte_carlo_cohorts_from_project(project_data, args.project)
            if len(cohorts) < 2:
                print(
                    "Error: Could not infer >=2 Monte Carlo cohorts from project. "
                    "Define project controls/diseases sample_paths (or flat groups) with CSVs.",
                    file=sys.stderr,
                )
                sys.exit(1)

            mc_config_dict = {
                "samples_base_path": project_data.get("samples_base_path", "/work/prostate-cancer/samples"),
                "base_project": str(args.project),
                "output_base": project_data.get("output_base", "/work/prostate-cancer"),
                "path_remap": project_data.get("path_remap"),
                "cohorts": cohorts,
                **validation_settings
            }
            config = MonteCarloConfig.model_validate(mc_config_dict)
        else:
            print(f"Error: Project {args.project} does not contain step_config.validation", file=sys.stderr)
            sys.exit(1)
    elif args.config is not None:
        # Regular dedicated MC config file
        config = MonteCarloConfig.from_json_file(args.config)
    else:
        parser.error("Either --config or --project must be provided")

    if args.iterations is not None:
        config.n_iterations = args.iterations
    if args.seed is not None:
        config.seed = args.seed
    if args.output_base is not None:
        config.output_base = str(args.output_base)
    if args.samples_base_path is not None:
        config = config.model_copy(update={"samples_base_path": str(args.samples_base_path)})
    if args.path_remap:
        merged = dict(config.path_remap or {})
        for item in args.path_remap:
            if "=" not in item:
                print(
                    f"Error: --path-remap must be OLD=NEW, got: {item!r}",
                    file=sys.stderr,
                )
                sys.exit(1)
            old_p, new_p = item.split("=", 1)
            if not old_p.strip():
                print(f"Error: empty OLD prefix in --path-remap: {item!r}", file=sys.stderr)
                sys.exit(1)
            merged[old_p] = new_p
        config = config.model_copy(update={"path_remap": merged})
    if args.stability:
        config.run_stability = True
    if args.stability_featurecuts:
        config = config.model_copy(update={"stability_featurecuts_enabled": True})
    if args.stability_target_ba is not None:
        config = config.model_copy(
            update={"stability_target_balanced_accuracy": float(args.stability_target_ba)}
        )
    if args.stability_min_selected_dmps is not None:
        config = config.model_copy(
            update={"stability_min_selected_dmps": int(args.stability_min_selected_dmps)}
        )
    if args.skip_enricher:
        config.skip_enricher = True
    if args.predictor_only:
        config.predictor_only = True
    if args.model_backend and args.post_model_backend and args.model_backend != args.post_model_backend:
        print(
            "Error: --model-backend and --post-model-backend must match when both are provided.",
            file=sys.stderr,
        )
        sys.exit(1)
    selected_backend = args.post_model_backend or args.model_backend
    if selected_backend:
        config = config.model_copy(update={"model_backend": selected_backend})
    if args.covariates_path is not None:
        config = config.model_copy(update={"covariates_path": str(args.covariates_path)})
    if args.tabular_max_dmps is not None:
        config = config.model_copy(update={"tabular_max_dmps": int(args.tabular_max_dmps)})
    if args.tabular_model_type:
        mt = str(args.tabular_model_type)
        config = config.model_copy(
            update={
                "tabular_model_type": mt,
                "tabular_methods": [{"method": mt, "params": {}}],
            }
        )
    if args.tabular_methods_json:
        try:
            parsed_methods = json.loads(str(args.tabular_methods_json))
        except Exception as e:
            print(f"Error: invalid --tabular-methods-json: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(parsed_methods, list) or not parsed_methods:
            print("Error: --tabular-methods-json must be a non-empty JSON array.", file=sys.stderr)
            sys.exit(1)
        config = config.model_copy(update={"tabular_methods": parsed_methods})
    if args.generative_latent_dim is not None:
        config = config.model_copy(update={"generative_latent_dim": int(args.generative_latent_dim)})
    if args.generative_kl_weight is not None:
        config = config.model_copy(update={"generative_kl_weight": float(args.generative_kl_weight)})
    if args.generative_density_type:
        config = config.model_copy(update={"generative_density_type": str(args.generative_density_type)})
    if args.generative_epochs is not None:
        config = config.model_copy(update={"generative_epochs": int(args.generative_epochs)})
    if args.generative_batch_size is not None:
        config = config.model_copy(update={"generative_batch_size": int(args.generative_batch_size)})
    if args.generative_seed is not None:
        config = config.model_copy(update={"generative_seed": int(args.generative_seed)})
    if args.generative_calibrate:
        config = config.model_copy(update={"generative_calibrate": True})
    if args.no_generative_covariates_strict:
        config = config.model_copy(update={"generative_covariates_strict": False})

    base_project = Path(config.base_project)
    if not base_project.is_file():
        print(f"Error: base_project not found: {base_project}", file=sys.stderr)
        sys.exit(1)

    base_project_config = load_project(config.base_project)
    output_base = Path(config.output_base)
    output_base.mkdir(parents=True, exist_ok=True)
    project_name = base_project_config.project_name
    monte_carlo_runs_root = output_base / project_name / "monte_carlo_runs"
    monte_carlo_runs_root.mkdir(parents=True, exist_ok=True)

    if args.resume is not None and (args.freeze or args.model):
        print("Error: --resume can only be used with Monte Carlo iteration modes (not --freeze/--model).", file=sys.stderr)
        sys.exit(1)
    if args.skip_centroid and (args.freeze or args.model or args.post_model_validation or args.model_mc):
        print("Error: --skip-centroid can only be used with Monte Carlo iteration mode.", file=sys.stderr)
        sys.exit(1)
    if args.skip_centroid and config.predictor_only:
        print("Error: --skip-centroid is incompatible with --predictor-only.", file=sys.stderr)
        sys.exit(1)
    if args.post_model_validation and (args.freeze or args.model):
        print("Error: --post-model-validation cannot be combined with --freeze or --model.", file=sys.stderr)
        sys.exit(1)
    if args.post_model_validation and args.predictor_only:
        print("Error: --post-model-validation cannot be combined with --predictor-only.", file=sys.stderr)
        sys.exit(1)
    if args.model_mc_all and not args.model_mc:
        print("Error: --model-mc-all requires --model-mc.", file=sys.stderr)
        sys.exit(1)
    if args.model_mc and args.post_model_validation:
        print("Error: --model-mc cannot be combined with --post-model-validation.", file=sys.stderr)
        sys.exit(1)
    if args.model_mc and args.predictor_only:
        print("Error: --model-mc cannot be combined with --predictor-only.", file=sys.stderr)
        sys.exit(1)
    if args.model_mc and args.model:
        print("Error: --model-mc cannot be combined with --model.", file=sys.stderr)
        sys.exit(1)
    if args.model_mc and args.freeze:
        print("Error: --model-mc cannot be combined with --freeze.", file=sys.stderr)
        sys.exit(1)
    if args.select_best_model and (args.freeze or args.model or args.post_model_validation or config.predictor_only):
        print(
            "Error: --select-best-model cannot be combined with --freeze/--model/--post-model-validation/--predictor-only.",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.rollout_compare and (
        args.freeze or args.model or args.model_mc or args.post_model_validation or args.select_best_model
    ):
        print(
            "Error: --rollout-compare cannot be combined with execution modes.",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.rollout_compare:
        if args.baseline_summary is None or args.candidate_summary is None:
            print(
                "Error: --rollout-compare requires --baseline-summary and --candidate-summary.",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            report = evaluate_dual_run(
                baseline_summary_path=args.baseline_summary,
                candidate_summary_path=args.candidate_summary,
                tolerances={
                    "balanced_accuracy_drop_max": config.rollout_balanced_accuracy_drop_max,
                    "macro_f1_drop_max": config.rollout_macro_f1_drop_max,
                    "nll_improvement_min_frac": config.rollout_nll_improvement_min_frac,
                    "brier_improvement_min_frac": config.rollout_brier_improvement_min_frac,
                    "ece_improvement_min_frac": config.rollout_ece_improvement_min_frac,
                },
            )
        except Exception as e:
            print(f"Error: rollout comparison failed: {e}", file=sys.stderr)
            sys.exit(1)
        report_path = (
            args.rollout_report
            if args.rollout_report is not None
            else (monte_carlo_runs_root / "rollout_decision.json")
        )
        write_rollout_report(report, report_path)
        print(f"Rollout recommendation: {report['recommendation']}")
        print(f"Wrote rollout report: {report_path}")
        print("Done.")
        return

    if args.freeze:
        if not config.freeze_stable_dmp_csv:
            config.freeze_stable_dmp_csv = str(monte_carlo_runs_root / "stability" / "stable_dmps_production.csv")
        if not Path(config.freeze_stable_dmp_csv).exists():
            print(
                f"Error: --freeze needs stable DMP CSV at {config.freeze_stable_dmp_csv} "
                "(run MC with --stability first, or set freeze_stable_dmp_csv).",
                file=sys.stderr,
            )
            sys.exit(1)

    if config.predictor_only and not config.frozen_project_path:
        default_frozen = monte_carlo_runs_root / "production" / "project.json"
        if default_frozen.is_file():
            config.frozen_project_path = str(default_frozen)
    if config.predictor_only and not config.frozen_project_path:
        print(
            "Error: predictor_only requires frozen_project_path in config or an existing "
            f"{monte_carlo_runs_root / 'production' / 'project.json'} from --freeze.",
            file=sys.stderr,
        )
        sys.exit(1)
    if config.predictor_only and not Path(config.frozen_project_path).is_file():
        print(f"Error: frozen_project_path not found: {config.frozen_project_path}", file=sys.stderr)
        sys.exit(1)

    try:
        assert_validation_predictor_accuracy_mode(
            base_project_config.get_step_config("predictor") or {}
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.freeze:
        stable_path = Path(config.freeze_stable_dmp_csv)
        print(f"Running production freeze using stable DMP panel: {stable_path}")
        production_summary = freeze_production_model(
            base_project=base_project,
            stable_dmp_csv=str(stable_path),
            monte_carlo_runs_root=monte_carlo_runs_root,
            production_output_dir=config.production_output_dir,
            config=config,
        )
        out = production_summary.get("output_dir", "unknown")
        if not production_summary.get("success", False):
            for err in production_summary.get("errors") or []:
                print(err, file=sys.stderr)
            print(
                f"Production freeze failed (see production_summary.json and logs under {out}).",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Production freeze complete. See: {out}")
        print("Done.")
        return
    elif args.model:
        try:
            assert_production_model_build_allowed(config)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Running production model build using project: {monte_carlo_runs_root / 'production' / 'project.json'}")
        production_summary = build_production_model(
            monte_carlo_runs_root=monte_carlo_runs_root,
            production_output_dir=config.production_output_dir,
            config=config,
        )
        out = production_summary.get("output_dir", "unknown")
        if not production_summary.get("success", False):
            for err in production_summary.get("errors") or []:
                print(err, file=sys.stderr)
            print(
                f"Production model build failed (see model_summary.json and logs under {out}).",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Production model build complete. See: {out}")
        print("Done.")
        return
    elif args.model_mc or args.select_best_model:
        production_dir = (
            Path(config.production_output_dir)
            if config.production_output_dir
            else (monte_carlo_runs_root / "production")
        )
        production_project = production_dir / "project.json"
        if not production_project.is_file():
            print(
                f"Error: model-mc requires production project at {production_project} (run --freeze first).",
                file=sys.stderr,
            )
            sys.exit(1)
        base_project_for_runs = production_project
        try:
            layout = infer_monte_carlo_layout(base_project_for_runs, len(config.cohorts))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        cohort_paths_list: List[Tuple[str, List[str]]] = []
        for c in config.cohorts:
            paths = load_and_resolve_sample_paths(c.csv, config.samples_base_path)
            if not paths:
                print(f"Error: cohort {c.label!r} ({c.csv}) must list at least one sample.", file=sys.stderr)
                sys.exit(1)
            cohort_paths_list.append((c.label, paths))
        cohort_labels = [c.label for c in config.cohorts]
        control_paths: List[str] = []
        disease_paths: List[str] = []
        if layout == "binary":
            control_paths = cohort_paths_list[0][1]
            disease_paths = cohort_paths_list[1][1]

        per_cancer_group = False

        model_mc_root = monte_carlo_runs_root / "model_mc"
        model_mc_root.mkdir(parents=True, exist_ok=True)
        _write_baseline_manifest(
            output_root=model_mc_root,
            mode="model_mc",
            config=config,
            layout=layout,
            cohort_paths_list=cohort_paths_list,
        )
        configured_backends = (
            ["ecdf", "tabular_sklearn", "generative_hybrid"]
            if args.model_mc_all
            else [str(config.model_backend or "ecdf").strip().lower()]
        )
        if args.select_best_model and not args.model_mc:
            discovered = [
                p.name
                for p in sorted(model_mc_root.iterdir())
                if p.is_dir() and p.name in {"ecdf", "tabular_sklearn", "generative_hybrid"}
            ]
            backends = discovered or configured_backends
        else:
            backends = configured_backends
        if args.model_mc:
            if args.model_mc_all:
                shared_root = model_mc_root / "shared"
                print(
                    f"Running model-mc shared iteration stage into {shared_root}",
                    file=sys.stderr,
                )
                try:
                    shared_rows = _build_model_mc_shared_runs(
                        base_project_for_runs=base_project_for_runs,
                        config=config,
                        layout=layout,
                        cohort_paths_list=cohort_paths_list,
                        cohort_labels=cohort_labels,
                        control_paths=control_paths,
                        disease_paths=disease_paths,
                        shared_root=shared_root,
                        resume_arg=args.resume,
                        per_cancer_group=per_cancer_group,
                    )
                except Exception as e:
                    print(f"Error: model-mc shared run stage failed: {e}", file=sys.stderr)
                    sys.exit(1)
                print("Completed model-mc shared iteration stage", file=sys.stderr)
                for backend in backends:
                    backend_root = model_mc_root / backend
                    print(
                        f"Running model-mc backend={backend} into {backend_root}",
                        file=sys.stderr,
                    )
                    try:
                        _run_model_mc_backend_from_shared_runs(
                            backend=backend,
                            config=config.model_copy(update={"model_backend": backend}),
                            layout=layout,
                            cohort_paths_list=cohort_paths_list,
                            backend_root=backend_root,
                            shared_root=shared_root,
                            shared_rows=shared_rows,
                            resume_arg=args.resume,
                            per_cancer_group=per_cancer_group,
                        )
                    except Exception as e:
                        print(f"Error: model-mc backend {backend} failed: {e}", file=sys.stderr)
                        sys.exit(1)
                    print(f"Completed model-mc backend={backend}", file=sys.stderr)
            else:
                shared_root = model_mc_root / "shared"
                use_shared_runs = shared_root.is_dir()
                shared_rows: List[Dict[str, Any]] = []
                if use_shared_runs:
                    try:
                        shared_rows = _load_model_mc_shared_rows(
                            shared_root=shared_root,
                            n_iterations=config.n_iterations,
                        )
                        print(
                            f"Reusing existing model-mc shared runs from {shared_root}",
                            file=sys.stderr,
                        )
                    except Exception as e:
                        print(
                            f"Warning: unable to reuse shared runs at {shared_root}: {e}. "
                            "Falling back to backend-local model-mc execution.",
                            file=sys.stderr,
                        )
                        use_shared_runs = False
                for backend in backends:
                    backend_root = model_mc_root / backend
                    print(
                        f"Running model-mc backend={backend} into {backend_root}",
                        file=sys.stderr,
                    )
                    try:
                        if use_shared_runs:
                            _run_model_mc_backend_from_shared_runs(
                                backend=backend,
                                config=config.model_copy(update={"model_backend": backend}),
                                layout=layout,
                                cohort_paths_list=cohort_paths_list,
                                backend_root=backend_root,
                                shared_root=shared_root,
                                shared_rows=shared_rows,
                                resume_arg=args.resume,
                                per_cancer_group=per_cancer_group,
                            )
                        else:
                            _run_model_mc_backend(
                                backend=backend,
                                base_project_for_runs=base_project_for_runs,
                                config=config.model_copy(update={"model_backend": backend}),
                                layout=layout,
                                cohort_paths_list=cohort_paths_list,
                                cohort_labels=cohort_labels,
                                control_paths=control_paths,
                                disease_paths=disease_paths,
                                backend_root=backend_root,
                                resume_arg=args.resume,
                                per_cancer_group=per_cancer_group,
                            )
                    except Exception as e:
                        print(f"Error: model-mc backend {backend} failed: {e}", file=sys.stderr)
                        sys.exit(1)
                    print(f"Completed model-mc backend={backend}", file=sys.stderr)

        if args.select_best_model:
            try:
                ranking = _write_backend_ranking(
                    model_mc_root=model_mc_root,
                    backends=backends,
                    metric=args.selection_metric,
                    stat=args.selection_stat,
                )
            except Exception as e:
                print(f"Error: backend ranking failed: {e}", file=sys.stderr)
                sys.exit(1)
            best = ranking[0]
            best_backend = str(best["backend"])
            print(
                f"Selected best backend: {best_backend} ({args.selection_metric} {args.selection_stat}={best['score']:.6f})",
                file=sys.stderr,
            )
            try:
                summary = build_production_model(
                    monte_carlo_runs_root=monte_carlo_runs_root,
                    production_output_dir=config.production_output_dir,
                    config=config.model_copy(update={"model_backend": best_backend}),
                )
            except Exception as e:
                print(f"Error: failed final all-data model build for backend={best_backend}: {e}", file=sys.stderr)
                sys.exit(1)
            if not summary.get("success", False):
                for err in summary.get("errors") or []:
                    print(err, file=sys.stderr)
                print(
                    f"Production model build failed for selected backend={best_backend}.",
                    file=sys.stderr,
                )
                sys.exit(1)
            import json

            selection_payload = {
                "selected_backend": best_backend,
                "selection_metric": args.selection_metric,
                "selection_stat": args.selection_stat,
                "ranking": ranking,
            }
            selection_path = production_dir / "selected_backend.json"
            with open(selection_path, "w", encoding="utf-8") as f:
                json.dump(selection_payload, f, indent=2)
            print(f"Wrote backend selection: {selection_path}")
            print(f"Production model build complete. See: {summary.get('output_dir', 'unknown')}")
            print("Done.")
            return

        print(f"Model-mc complete. See: {model_mc_root}")
        print("Done.")
        return
    elif args.post_model_validation:
        try:
            assert_production_model_build_allowed(config)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        production_dir = (
            Path(config.production_output_dir)
            if config.production_output_dir
            else (monte_carlo_runs_root / "production")
        )
        production_project = production_dir / "project.json"
        if not production_project.is_file():
            print(
                f"Error: post-model validation requires production project at {production_project} (run --freeze first).",
                file=sys.stderr,
            )
            sys.exit(1)
        if (config.model_backend or "ecdf").strip().lower() in {"tabular_sklearn", "generative_hybrid"}:
            model_dir = production_dir / "classifiers"
            if not model_dir.is_dir():
                print(
                    f"Error: post-model validation requires trained backend model artifacts under {model_dir} "
                    "(run --model first).",
                    file=sys.stderr,
                )
                sys.exit(1)

        try:
            layout = infer_monte_carlo_layout(base_project, len(config.cohorts))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        cohort_paths_list: List[Tuple[str, List[str]]] = []
        for c in config.cohorts:
            paths = load_and_resolve_sample_paths(c.csv, config.samples_base_path)
            if not paths:
                print(f"Error: cohort {c.label!r} ({c.csv}) must list at least one sample.", file=sys.stderr)
                sys.exit(1)
            cohort_paths_list.append((c.label, paths))
        cohort_labels = [c.label for c in config.cohorts]
        control_paths: List[str] = []
        disease_paths: List[str] = []
        if layout == "binary":
            control_paths = cohort_paths_list[0][1]
            disease_paths = cohort_paths_list[1][1]

        post_model_root = monte_carlo_runs_root / "post_model_validation"
        post_model_root.mkdir(parents=True, exist_ok=True)
        _write_baseline_manifest(
            output_root=post_model_root,
            mode="post_model_validation",
            config=config,
            layout=layout,
            cohort_paths_list=cohort_paths_list,
        )

        rows: List[Dict[str, Any]] = []
        all_timings: List[Dict[str, Any]] = []
        existing_runs = _list_existing_run_numbers(post_model_root)
        try:
            start_iteration_idx = _resolve_resume_start_iteration(
                args.resume,
                n_iterations=config.n_iterations,
                existing_runs=existing_runs,
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        if args.resume is not None:
            for n in existing_runs:
                if n >= (start_iteration_idx + 1):
                    run_dir = post_model_root / f"run_{n:04d}"
                    if run_dir.is_dir():
                        shutil.rmtree(run_dir)
            resume_label = "auto" if args.resume == 0 else str(args.resume)
            print(
                f"Resuming post-model validation (--resume {resume_label}): "
                f"starting at run_{start_iteration_idx + 1:04d} through run_{config.n_iterations:04d}",
                file=sys.stderr,
            )

        use_rich = sys.stderr.isatty()
        console = Console(file=sys.stderr) if use_rich else None
        n_step_tasks = 1
        if use_rich and console is not None:
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=40),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console,
                expand=False,
            )
        else:
            progress = None

        completed_iteration_seconds: List[float] = []
        with (progress if progress is not None else nullcontext()):
            if progress is not None:
                task_iter = progress.add_task("Post-model iterations", total=config.n_iterations, completed=start_iteration_idx)
            else:
                task_iter = None

            for i in range(start_iteration_idx, config.n_iterations):
                iteration_t0 = time.perf_counter()
                run_id = f"run_{i + 1:04d}"
                run_dir = post_model_root / run_id
                seed_i = (config.seed + i) if config.seed is not None else None
                if progress is not None:
                    task_steps = progress.add_task("Steps", total=n_step_tasks, completed=0)
                    task_current = progress.add_task("Running…", total=None, visible=False)

                    def make_progress_cb(prog: Progress, t_steps: Any, t_cur: Any):
                        def progress_cb(step_index: int, step_name: str, event: str) -> None:
                            if event == "start":
                                prog.update(t_steps, description=f"Steps ({step_name})")
                                prog.update(t_cur, description=f"Running {step_name}…", visible=True)
                            else:
                                prog.advance(t_steps, 1)
                                prog.update(t_cur, visible=False)
                        return progress_cb

                    progress_callback = make_progress_cb(progress, task_steps, task_current)
                else:
                    task_steps = task_current = None
                    progress_callback = None

                train_m: Dict[str, List[str]] = {}
                val_m: Dict[str, List[str]] = {}
                try:
                    if layout == "binary":
                        train_control, train_disease, val_control, val_disease = stratified_split(
                            control_paths,
                            disease_paths,
                            config.train_fraction,
                            seed=seed_i,
                        )
                    else:
                        train_m, val_m = stratified_split_multiclass(
                            cohort_paths_list,
                            config.train_fraction,
                            seed=seed_i,
                        )
                except ValueError as e:
                    print(f"Warning: iteration {i + 1} skipped: {e}", file=sys.stderr)
                    elapsed = time.perf_counter() - iteration_t0
                    eta = _estimate_iteration_eta(completed_iteration_seconds, config.n_iterations - (i + 1))
                    if progress is None:
                        print(
                            f"Post-model iteration {i + 1}/{config.n_iterations} skipped ({run_id}) "
                            f"in {_format_duration(elapsed)} (ETA {eta})",
                            file=sys.stderr,
                        )
                    if progress is not None:
                        progress.remove_task(task_steps)
                        progress.remove_task(task_current)
                        progress.advance(task_iter, 1)
                    continue

                if layout == "binary":
                    (
                        project_path,
                        _,
                        _,
                        val_control_csv,
                        val_disease_csv,
                        _,
                        _,
                    ) = generate_run_project(
                        base_project,
                        run_dir,
                        run_id,
                        str(post_model_root),
                        train_control,
                        train_disease,
                        val_control,
                        val_disease,
                        config.samples_base_path,
                    )
                    if (config.model_backend or "ecdf").strip().lower() == "ecdf":
                        apply_frozen_pipeline_artifacts_to_run_project(project_path, production_project)
                    run_project = load_project(project_path)
                    comparisons = run_project.get_comparisons()
                    if comparisons:
                        spec = comparisons[0]
                        predictor_output_dir = run_dir / "predictors" / spec.control_group / spec.disease_group
                    else:
                        predictor_output_dir = run_dir / "predictors"
                    n_train_samples = len(train_control) + len(train_disease)
                    n_val_samples = len(val_control) + len(val_disease)
                    success, errors, step_timings = run_post_model_validation_binary(
                        project_json=project_path,
                        val_control_csv=val_control_csv,
                        val_disease_csv=val_disease_csv,
                        predictor_output_dir=predictor_output_dir,
                        production_output_dir=production_dir,
                        logs_dir=run_dir / "logs",
                        progress_callback=progress_callback,
                        config=config,
                    )
                else:
                    if layout == "multiclass":
                        project_path, val_groups_json = generate_run_project_multiclass(
                            base_project,
                            run_dir,
                            run_id,
                            str(post_model_root),
                            train_m,
                            val_m,
                            cohort_labels,
                            config.samples_base_path,
                        )
                    else:
                        project_path, val_groups_json = generate_run_project_hierarchical_multiclass(
                            base_project,
                            run_dir,
                            run_id,
                            str(post_model_root),
                            train_m,
                            val_m,
                            cohort_labels,
                            config.samples_base_path,
                        )
                    if (config.model_backend or "ecdf").strip().lower() == "ecdf":
                        apply_frozen_pipeline_artifacts_to_run_project(project_path, production_project)
                    predictor_output_dir = run_dir / "predictors"
                    n_train_samples = sum(len(train_m[k]) for k in cohort_labels)
                    n_val_samples = sum(len(val_m[k]) for k in cohort_labels)
                    success, errors, step_timings = run_post_model_validation_multiclass(
                        project_json=project_path,
                        test_groups_json=val_groups_json,
                        predictor_output_dir=predictor_output_dir,
                        production_output_dir=production_dir,
                        logs_dir=run_dir / "logs",
                        progress_callback=progress_callback,
                        config=config,
                    )

                if progress is not None:
                    progress.remove_task(task_steps)
                    progress.remove_task(task_current)
                for t in step_timings:
                    all_timings.append({
                        **t,
                        "run_id": run_id,
                        "run_dir": str(run_dir),
                        "n_train_samples": n_train_samples,
                        "n_val_samples": n_val_samples,
                    })
                elapsed = time.perf_counter() - iteration_t0
                completed_iteration_seconds.append(elapsed)

                if not success:
                    for msg in errors:
                        print(f"Error [{run_id}]: {msg}", file=sys.stderr)
                    if config.abort_on_step_failure:
                        print("Aborting (abort_on_step_failure=true).", file=sys.stderr)
                        sys.exit(1)
                    if progress is not None:
                        progress.advance(task_iter, 1)
                    else:
                        eta = _estimate_iteration_eta(completed_iteration_seconds, config.n_iterations - (i + 1))
                        print(
                            f"Post-model iteration {i + 1}/{config.n_iterations} failed ({run_id}) "
                            f"in {_format_duration(elapsed)} (ETA {eta})",
                            file=sys.stderr,
                        )
                    continue

                scalar = iteration_scalar_metrics_from_run_dir(run_dir)
                rows.append({"iteration": i + 1, "run_id": run_id, "run_dir": str(run_dir), **scalar})
                if progress is None:
                    eta = _estimate_iteration_eta(completed_iteration_seconds, config.n_iterations - (i + 1))
                    print(
                        f"Completed post-model iteration {i + 1}/{config.n_iterations} ({run_id}) "
                        f"in {_format_duration(elapsed)} (ETA {eta})",
                        file=sys.stderr,
                    )
                else:
                    progress.advance(task_iter, 1)

        if not rows:
            print("No successful post-model iterations; nothing to aggregate.", file=sys.stderr)
            sys.exit(1)
        df = build_metrics_table(rows)
        all_metrics_csv = post_model_root / "all_metrics.csv"
        write_all_metrics_csv(df, all_metrics_csv)
        summary = compute_summary(df)
        summary_path = post_model_root / "metrics_summary.json"
        write_summary_json(summary, summary_path)
        if all_timings:
            step_timings_path = post_model_root / "step_timings.csv"
            write_step_timings_csv(all_timings, step_timings_path)
            resource_summary = compute_resource_summary(all_timings)
            if resource_summary:
                write_resource_summary_json(resource_summary, post_model_root / "resource_summary.json")
        chart_path = post_model_root / "metrics_distributions_plotly.html"
        write_metrics_distribution_plotly(df, chart_path)
        print(f"Post-model validation complete. See: {post_model_root}")
        print(f"Wrote {all_metrics_csv}")
        print(f"Wrote {summary_path}")
        print(f"Wrote {chart_path}")
        print("Done.")
        return
    try:
        layout = infer_monte_carlo_layout(base_project, len(config.cohorts))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    cohort_paths_list: List[Tuple[str, List[str]]] = []
    for c in config.cohorts:
        paths = load_and_resolve_sample_paths(c.csv, config.samples_base_path)
        if not paths:
            print(f"Error: cohort {c.label!r} ({c.csv}) must list at least one sample.", file=sys.stderr)
            sys.exit(1)
        cohort_paths_list.append((c.label, paths))

    cohort_labels = [c.label for c in config.cohorts]
    control_paths: List[str] = []
    disease_paths: List[str] = []
    if layout == "binary":
        control_paths = cohort_paths_list[0][1]
        disease_paths = cohort_paths_list[1][1]
    _write_baseline_manifest(
        output_root=monte_carlo_runs_root,
        mode="monte_carlo",
        config=config,
        layout=layout,
        cohort_paths_list=cohort_paths_list,
    )

    # Optional: base project has multiple disease groups -> use --per-cancer-group (we generate single comparison, so no)
    per_cancer_group = False

    use_rich = sys.stderr.isatty()
    console = Console(file=sys.stderr) if use_rich else None

    rows: List[Dict[str, Any]] = []
    all_timings: List[Dict[str, Any]] = []
    existing_runs = _list_existing_run_numbers(monte_carlo_runs_root)
    try:
        start_iteration_idx = _resolve_resume_start_iteration(
            args.resume,
            n_iterations=config.n_iterations,
            existing_runs=existing_runs,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if args.resume is not None and start_iteration_idx > 0:
        for prev_i in range(start_iteration_idx):
            prev_run_id = f"run_{prev_i + 1:04d}"
            prev_run_dir = monte_carlo_runs_root / prev_run_id
            if not prev_run_dir.is_dir():
                continue
            prev_scalar = iteration_scalar_metrics_from_run_dir(prev_run_dir)
            if prev_scalar:
                rows.append(
                    {
                        "iteration": prev_i + 1,
                        "run_id": prev_run_id,
                        "run_dir": str(prev_run_dir),
                        **prev_scalar,
                    }
                )
        all_timings.extend(
            _load_existing_step_timings(
                monte_carlo_runs_root / "step_timings.csv",
                keep_until_iteration_exclusive=start_iteration_idx + 1,
            )
        )
    if args.resume is not None:
        for n in existing_runs:
            if n >= (start_iteration_idx + 1):
                run_dir = monte_carlo_runs_root / f"run_{n:04d}"
                if run_dir.is_dir():
                    shutil.rmtree(run_dir)
        resume_label = "auto" if args.resume == 0 else str(args.resume)
        print(
            f"Resuming Monte Carlo iterations (--resume {resume_label}): "
            f"starting at run_{start_iteration_idx + 1:04d} through run_{config.n_iterations:04d}",
            file=sys.stderr,
        )
    previous_train_control: List[str] | None = None
    previous_train_disease: List[str] | None = None

    n_step_tasks = 1 if config.predictor_only else (
        (5 if config.skip_enricher else 6) if config.run_mapper_and_enricher else 4
    )

    if use_rich and console is not None:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=False,
        )
    else:
        progress = None

    with (progress if progress is not None else nullcontext()):
        if progress is not None:
            task_iter = progress.add_task("Iterations", total=config.n_iterations, completed=start_iteration_idx)
        else:
            task_iter = None

        completed_iteration_seconds: List[float] = []
        for i in range(start_iteration_idx, config.n_iterations):
            iteration_t0 = time.perf_counter()
            run_id = f"run_{i + 1:04d}"
            run_dir = monte_carlo_runs_root / run_id
            seed_i = (config.seed + i) if config.seed is not None else None
            detector_step_override = _write_detector_featurecuts_override(run_dir, config)

            if progress is not None:
                task_steps = progress.add_task("Steps", total=n_step_tasks, completed=0)
                task_current = progress.add_task("Running…", total=None, visible=False)

                def make_progress_cb(prog: Progress, t_steps: Any, t_cur: Any):
                    def progress_cb(step_index: int, step_name: str, event: str) -> None:
                        if event == "start":
                            prog.update(t_steps, description=f"Steps ({step_name})")
                            prog.update(t_cur, description=f"Running {step_name}…", visible=True)
                        else:
                            prog.advance(t_steps, 1)
                            prog.update(t_cur, visible=False)
                    return progress_cb

                progress_callback = make_progress_cb(progress, task_steps, task_current)
            else:
                task_steps = task_current = None
                progress_callback = None

            train_m: Dict[str, List[str]] = {}
            val_m: Dict[str, List[str]] = {}
            val_control_csv: Path | None = None
            val_disease_csv: Path | None = None
            val_groups_json: Path | None = None
            centroid_group1_override: Path | None = None
            centroid_group2_override: Path | None = None

            try:
                if not args.skip_centroid:
                    if layout == "binary":
                        train_control, train_disease, val_control, val_disease = stratified_split(
                            control_paths,
                            disease_paths,
                            config.train_fraction,
                            seed=seed_i,
                        )
                    elif layout in ("multiclass", "hierarchical_multiclass"):
                        train_m, val_m = stratified_split_multiclass(
                            cohort_paths_list,
                            config.train_fraction,
                            seed=seed_i,
                        )
                    else:
                        raise RuntimeError(f"unknown Monte Carlo layout: {layout}")
            except ValueError as e:
                print(f"Warning: iteration {i + 1} skipped: {e}", file=sys.stderr)
                if progress is None:
                    elapsed = time.perf_counter() - iteration_t0
                    eta = _estimate_iteration_eta(
                        completed_iteration_seconds,
                        config.n_iterations - (i + 1),
                    )
                    print(
                        f"Iteration {i + 1}/{config.n_iterations} skipped ({run_id}) "
                        f"in {_format_duration(elapsed)} (ETA {eta})",
                        file=sys.stderr,
                    )
                if progress is not None:
                    progress.remove_task(task_steps)
                    progress.remove_task(task_current)
                    progress.advance(task_iter, 1)
                continue

            if layout == "binary":
                if args.skip_centroid:
                    project_path = run_dir / "project.json"
                    if not project_path.is_file():
                        print(
                            f"Warning: iteration {i + 1} skipped: missing existing run project at {project_path} "
                            "(run without --skip-centroid first).",
                            file=sys.stderr,
                        )
                        if progress is None:
                            elapsed = time.perf_counter() - iteration_t0
                            eta = _estimate_iteration_eta(
                                completed_iteration_seconds,
                                config.n_iterations - (i + 1),
                            )
                            print(
                                f"Iteration {i + 1}/{config.n_iterations} skipped ({run_id}) "
                                f"in {_format_duration(elapsed)} (ETA {eta})",
                                file=sys.stderr,
                            )
                        if progress is not None:
                            progress.remove_task(task_steps)
                            progress.remove_task(task_current)
                            progress.advance(task_iter, 1)
                        continue
                    run_project = load_project(project_path)
                    comparisons = run_project.get_comparisons()
                    if comparisons:
                        spec = comparisons[0]
                        predictor_output_dir = run_dir / "predictors" / spec.control_group / spec.disease_group
                    else:
                        predictor_output_dir = run_dir / "predictors"
                    n_train_samples, n_val_samples = _count_run_samples_from_existing_files(run_dir)
                else:
                    (
                        project_path,
                        _,
                        _,
                        val_control_csv,
                        val_disease_csv,
                        centroid_group1_override,
                        centroid_group2_override,
                    ) = generate_run_project(
                        base_project,
                        run_dir,
                        run_id,
                        str(monte_carlo_runs_root),
                        train_control,
                        train_disease,
                        val_control,
                        val_disease,
                        config.samples_base_path,
                        previous_train_control_paths=previous_train_control,
                        previous_train_disease_paths=previous_train_disease,
                    )
                    previous_train_control = list(train_control)
                    previous_train_disease = list(train_disease)
                    if config.predictor_only:
                        apply_frozen_pipeline_artifacts_to_run_project(
                            project_path, Path(config.frozen_project_path)
                        )
                    run_project = load_project(project_path)
                    comparisons = run_project.get_comparisons()
                    if comparisons:
                        spec = comparisons[0]
                        predictor_output_dir = run_dir / "predictors" / spec.control_group / spec.disease_group
                    else:
                        predictor_output_dir = run_dir / "predictors"
                    n_train_samples = len(train_control) + len(train_disease)
                    n_val_samples = len(val_control) + len(val_disease)
                if config.predictor_only:
                    success, errors, step_timings = run_predictor_only_binary(
                        project_path,
                        val_control_csv,
                        val_disease_csv,
                        predictor_output_dir,
                        logs_dir=run_dir / "logs",
                        progress_callback=progress_callback,
                    )
                else:
                    success, errors, step_timings = run_pipeline_for_iteration(
                        project_path,
                        per_cancer_group=per_cancer_group,
                        logs_dir=run_dir / "logs",
                        progress_callback=progress_callback,
                        centroid_step_overrides={
                            "group1": centroid_group1_override,
                            "group2": centroid_group2_override,
                        },
                        detector_step_override=detector_step_override,
                        skip_centroid=bool(args.skip_centroid),
                        config=config,
                    )
            elif layout == "multiclass":
                if args.skip_centroid:
                    project_path = run_dir / "project.json"
                    val_groups_json = run_dir / "val_test_groups.json"
                    if not project_path.is_file():
                        print(
                            f"Warning: iteration {i + 1} skipped: missing existing run project at {project_path} "
                            "(run without --skip-centroid first).",
                            file=sys.stderr,
                        )
                        if progress is None:
                            elapsed = time.perf_counter() - iteration_t0
                            eta = _estimate_iteration_eta(
                                completed_iteration_seconds,
                                config.n_iterations - (i + 1),
                            )
                            print(
                                f"Iteration {i + 1}/{config.n_iterations} skipped ({run_id}) "
                                f"in {_format_duration(elapsed)} (ETA {eta})",
                                file=sys.stderr,
                            )
                        if progress is not None:
                            progress.remove_task(task_steps)
                            progress.remove_task(task_current)
                            progress.advance(task_iter, 1)
                        continue
                    predictor_output_dir = run_dir / "predictors"
                    n_train_samples, n_val_samples = _count_run_samples_from_existing_files(run_dir)
                else:
                    project_path, val_groups_json = generate_run_project_multiclass(
                        base_project,
                        run_dir,
                        run_id,
                        str(monte_carlo_runs_root),
                        train_m,
                        val_m,
                        cohort_labels,
                        config.samples_base_path,
                    )
                    predictor_output_dir = run_dir / "predictors"
                    n_train_samples = sum(len(train_m[k]) for k in cohort_labels)
                    n_val_samples = sum(len(val_m[k]) for k in cohort_labels)
                if config.predictor_only:
                    apply_frozen_pipeline_artifacts_to_run_project(
                        project_path, Path(config.frozen_project_path)
                    )
                    success, errors, step_timings = run_predictor_only_multiclass(
                        project_path,
                        val_groups_json,
                        predictor_output_dir,
                        logs_dir=run_dir / "logs",
                        progress_callback=progress_callback,
                    )
                else:
                    success, errors, step_timings = run_pipeline_for_iteration_multiclass(
                        project_path,
                        per_cancer_group=per_cancer_group,
                        logs_dir=run_dir / "logs",
                        progress_callback=progress_callback,
                        detector_step_override=detector_step_override,
                        skip_centroid=bool(args.skip_centroid),
                        config=config,
                    )
            else:
                if args.skip_centroid:
                    project_path = run_dir / "project.json"
                    val_groups_json = run_dir / "val_test_groups.json"
                    if not project_path.is_file():
                        print(
                            f"Warning: iteration {i + 1} skipped: missing existing run project at {project_path} "
                            "(run without --skip-centroid first).",
                            file=sys.stderr,
                        )
                        if progress is None:
                            elapsed = time.perf_counter() - iteration_t0
                            eta = _estimate_iteration_eta(
                                completed_iteration_seconds,
                                config.n_iterations - (i + 1),
                            )
                            print(
                                f"Iteration {i + 1}/{config.n_iterations} skipped ({run_id}) "
                                f"in {_format_duration(elapsed)} (ETA {eta})",
                                file=sys.stderr,
                            )
                        if progress is not None:
                            progress.remove_task(task_steps)
                            progress.remove_task(task_current)
                            progress.advance(task_iter, 1)
                        continue
                    predictor_output_dir = run_dir / "predictors"
                    n_train_samples, n_val_samples = _count_run_samples_from_existing_files(run_dir)
                else:
                    project_path, val_groups_json = generate_run_project_hierarchical_multiclass(
                        base_project,
                        run_dir,
                        run_id,
                        str(monte_carlo_runs_root),
                        train_m,
                        val_m,
                        cohort_labels,
                        config.samples_base_path,
                    )
                    predictor_output_dir = run_dir / "predictors"
                    n_train_samples = sum(len(train_m[k]) for k in cohort_labels)
                    n_val_samples = sum(len(val_m[k]) for k in cohort_labels)
                if config.predictor_only:
                    apply_frozen_pipeline_artifacts_to_run_project(
                        project_path, Path(config.frozen_project_path)
                    )
                    success, errors, step_timings = run_predictor_only_multiclass(
                        project_path,
                        val_groups_json,
                        predictor_output_dir,
                        logs_dir=run_dir / "logs",
                        progress_callback=progress_callback,
                    )
                else:
                    success, errors, step_timings = run_pipeline_for_iteration_multiclass(
                        project_path,
                        per_cancer_group=True,
                        logs_dir=run_dir / "logs",
                        progress_callback=progress_callback,
                        detector_step_override=detector_step_override,
                        skip_centroid=bool(args.skip_centroid),
                        config=config,
                    )
            if progress is not None:
                progress.remove_task(task_steps)
                progress.remove_task(task_current)
            for t in step_timings:
                all_timings.append({
                    **t,
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "n_train_samples": n_train_samples,
                    "n_val_samples": n_val_samples,
                })
            if not success:
                elapsed = time.perf_counter() - iteration_t0
                completed_iteration_seconds.append(elapsed)
                for msg in errors:
                    print(f"Error [{run_id}]: {msg}", file=sys.stderr)
                if config.abort_on_step_failure:
                    print("Aborting (abort_on_step_failure=true).", file=sys.stderr)
                    sys.exit(1)
                if progress is not None:
                    progress.advance(task_iter, 1)
                else:
                    eta = _estimate_iteration_eta(
                        completed_iteration_seconds,
                        config.n_iterations - (i + 1),
                    )
                    print(
                        f"Iteration {i + 1}/{config.n_iterations} failed ({run_id}) "
                        f"in {_format_duration(elapsed)} (ETA {eta})",
                        file=sys.stderr,
                    )
                continue

            scalar = iteration_scalar_metrics_from_run_dir(run_dir)
            row = {"iteration": i + 1, "run_id": run_id, "run_dir": str(run_dir), **scalar}
            rows.append(row)
            elapsed = time.perf_counter() - iteration_t0
            completed_iteration_seconds.append(elapsed)
            if progress is None:
                eta = _estimate_iteration_eta(
                    completed_iteration_seconds,
                    config.n_iterations - (i + 1),
                )
                print(
                    f"Completed iteration {i + 1}/{config.n_iterations} ({run_id}) "
                    f"in {_format_duration(elapsed)} (ETA {eta})",
                    file=sys.stderr,
                )
            else:
                progress.advance(task_iter, 1)

    if not rows:
        print("No successful iterations; nothing to aggregate.", file=sys.stderr)
        sys.exit(1)

    if args.stability or config.run_stability:
        print("\nRunning stability analysis on discovery outputs...")
        stability_summary = run_stability_analysis(
            monte_carlo_runs_root=monte_carlo_runs_root,
            dmp_min_freq=config.stability_dmp_freq,
            gene_min_freq=config.stability_gene_freq,
            min_balanced_accuracy=config.stability_min_balanced_accuracy,
            prefer_classifier_panel_dmps=bool(config.stability_featurecuts_enabled),
            dual_cutoff_enabled=bool(config.stability_dual_cutoff_enabled),
            relaxed_cutoff_mode=config.stability_relaxed_cutoff_mode,
            relaxed_multiplier=config.stability_relaxed_multiplier,
            score_eps=config.stability_score_eps,
            tiered_stability_enabled=bool(config.stability_tiers_enabled),
            tier_core_frequency=config.stability_tier_core_freq,
            tier_extended_frequency=config.stability_tier_extended_freq,
            tier_exploratory_frequency=config.stability_tier_exploratory_freq,
            default_freeze_tier=config.stability_default_freeze_tier,
        )
        print(f"Stability analysis complete. See: {stability_summary['output_dir']}")
        print(f"  Stable DMPs: {stability_summary['dmp_stability'].get('stable_dmps_at_threshold', 0)}")
        if stability_summary.get("tiered_stability_enabled"):
            print(
                f"  Tiered panels enabled (default freeze tier: {stability_summary.get('stability_default_freeze_tier')})"
            )
            tiers = stability_summary.get("stability_tiers") or {}
            for tier_name in ("core", "extended", "exploratory"):
                tier = tiers.get(tier_name) or {}
                if not tier:
                    continue
                print(
                    f"    {tier_name}: min_freq={tier.get('min_frequency')} "
                    f"strict={tier.get('n_strict_selected')} relaxed={tier.get('n_relaxed_selected')}"
                )
        gs = stability_summary.get("gene_stability") or {}
        print(f"  Stable genes: {gs.get('stable_genes_at_threshold', 0)} (non-zero only if enricher ran in iterations)")

    df = build_metrics_table(rows)
    all_metrics_csv = monte_carlo_runs_root / "all_metrics.csv"
    write_all_metrics_csv(df, all_metrics_csv)
    print(f"Wrote {all_metrics_csv}")

    summary = compute_summary(df)
    summary_path = monte_carlo_runs_root / "metrics_summary.json"
    write_summary_json(summary, summary_path)
    print(f"Wrote {summary_path}")

    if all_timings:
        step_timings_path = monte_carlo_runs_root / "step_timings.csv"
        write_step_timings_csv(all_timings, step_timings_path)
        print(f"Wrote {step_timings_path}")
        resource_summary = compute_resource_summary(all_timings)
        if resource_summary:
            resource_summary_path = monte_carlo_runs_root / "resource_summary.json"
            write_resource_summary_json(resource_summary, resource_summary_path)
            print(f"Wrote {resource_summary_path}")

    print("Done.")


if __name__ == "__main__":
    main()
