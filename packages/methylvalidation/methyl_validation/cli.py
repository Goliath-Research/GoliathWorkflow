"""
CLI for Monte Carlo validation runner.
"""

import argparse
import csv
import re
import shutil
import sys
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


_RUN_ID_RE = re.compile(r"^run_(\d{4})$")


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
        "--model-backend",
        choices=["ecdf", "tabular_sklearn", "generative_hybrid"],
        default=None,
        help="Override validation.model_backend for --model (default: ecdf).",
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
    if args.model_backend:
        config = config.model_copy(update={"model_backend": args.model_backend})
    if args.covariates_path is not None:
        config = config.model_copy(update={"covariates_path": str(args.covariates_path)})
    if args.tabular_max_dmps is not None:
        config = config.model_copy(update={"tabular_max_dmps": int(args.tabular_max_dmps)})
    if args.tabular_model_type:
        config = config.model_copy(update={"tabular_model_type": str(args.tabular_model_type)})
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
        print("Error: --resume can only be used with Monte Carlo iteration mode (not --freeze/--model).", file=sys.stderr)
        sys.exit(1)
    if args.skip_centroid and (args.freeze or args.model):
        print("Error: --skip-centroid can only be used with Monte Carlo iteration mode.", file=sys.stderr)
        sys.exit(1)
    if args.skip_centroid and config.predictor_only:
        print("Error: --skip-centroid is incompatible with --predictor-only.", file=sys.stderr)
        sys.exit(1)

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
        assert_monte_carlo_predictor_allowed(
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

        for i in range(start_iteration_idx, config.n_iterations):
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
            prefer_classifier_panel_dmps=bool(config.stability_featurecuts_enabled),
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
