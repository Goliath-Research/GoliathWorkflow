"""
CLI for Monte Carlo validation runner.
"""

import argparse
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
from .predictor_policy import assert_monte_carlo_predictor_allowed
from .pipeline_runner import (
    run_pipeline_for_iteration,
    run_pipeline_for_iteration_multiclass,
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
    write_all_metrics_csv,
    write_resource_summary_json,
    write_step_timings_csv,
    write_summary_json,
)
from .stability import run_stability_analysis, freeze_production_model, build_production_model


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
        help="After main analysis, run stability on discovery DMPs from centroid+detector iterations (classifier/predictor via --model).",
    )
    parser.add_argument(
        "--skip-enricher",
        action="store_true",
        help="Skip methyl-enricher step (useful when Grok API calls are slow).",
    )
    parser.add_argument(
        "--freeze",
        action="store_true",
        help="Run production freeze: centroid→detector(fixed panel)→mapper→enricher (no classifier/predictor).",
    )
    parser.add_argument(
        "--model",
        action="store_true",
        help="Build production model and predict: runs classifier and predictor on the production project (after --freeze).",
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
    if getattr(args, "samples_base_path", None) is not None:
        config = config.model_copy(update={"samples_base_path": str(args.samples_base_path)})
    if getattr(args, "path_remap", None):
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
    if getattr(args, "skip_enricher", False):
        config.skip_enricher = True
    if getattr(args, "predictor_only", False):
        config.predictor_only = True

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

    if getattr(args, "freeze", False):
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
        assert_monte_carlo_predictor_allowed(
            base_project_config.get_step_config("predictor") or {}
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "freeze", False):
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
    elif getattr(args, "model", False):
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

    # Optional: base project has multiple disease groups -> use --per-cancer-group (we generate single comparison, so no)
    per_cancer_group = False

    use_rich = sys.stderr.isatty()
    console = Console(file=sys.stderr) if use_rich else None

    rows: List[Dict[str, Any]] = []
    all_timings: List[Dict[str, Any]] = []
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
            task_iter = progress.add_task("Iterations", total=config.n_iterations)
        else:
            task_iter = None

        for i in range(config.n_iterations):
            run_id = f"run_{i + 1:04d}"
            run_dir = monte_carlo_runs_root / run_id
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
            val_control_csv: Path | None = None
            val_disease_csv: Path | None = None
            val_groups_json: Path | None = None
            centroid_group1_override: Path | None = None
            centroid_group2_override: Path | None = None

            try:
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
                comparisons = run_project.get_comparisons() if getattr(run_project, "get_comparisons", None) else []
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
                        config=config,
                    )
            elif layout == "multiclass":
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
                        config=config,
                    )
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
                for msg in errors:
                    print(f"Error [{run_id}]: {msg}", file=sys.stderr)
                if config.abort_on_step_failure:
                    print("Aborting (abort_on_step_failure=true).", file=sys.stderr)
                    sys.exit(1)
                if progress is not None:
                    progress.advance(task_iter, 1)
                continue

            scalar = iteration_scalar_metrics_from_run_dir(run_dir)
            row = {"iteration": i + 1, "run_id": run_id, "run_dir": str(run_dir), **scalar}
            rows.append(row)
            if progress is None:
                print(f"Completed iteration {i + 1}/{config.n_iterations} ({run_id})", file=sys.stderr)
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
        )
        print(f"Stability analysis complete. See: {stability_summary['output_dir']}")
        print(f"  Stable DMPs: {stability_summary['dmp_stability'].get('stable_dmps_at_threshold', 0)}")
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
