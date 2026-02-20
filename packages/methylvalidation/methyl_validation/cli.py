"""
CLI for Monte Carlo validation runner.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

from tqdm import tqdm

from .config import MonteCarloConfig
from .pipeline_runner import run_pipeline_for_iteration
from .project_gen import generate_run_project
from .split import load_and_resolve_sample_paths, stratified_split
from .validator_metrics import (
    _scalar_metrics_from_dict,
    build_metrics_table,
    compute_summary,
    load_metrics_from_json,
    write_all_metrics_csv,
    write_step_timings_csv,
    write_summary_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monte Carlo validation: stratified train/val splits, run pipeline per iteration, aggregate validator metrics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        required=True,
        help="Path to Monte Carlo config JSON.",
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
    args = parser.parse_args()

    config = MonteCarloConfig.from_json_file(args.config)
    if args.iterations is not None:
        config.n_iterations = args.iterations
    if args.seed is not None:
        config.seed = args.seed
    if args.output_base is not None:
        config.output_base = str(args.output_base)

    output_base = Path(config.output_base)
    output_base.mkdir(parents=True, exist_ok=True)

    # Load and resolve sample paths once
    control_paths = load_and_resolve_sample_paths(config.healthy_csv, config.samples_base_path)
    disease_paths = load_and_resolve_sample_paths(config.disease_csv, config.samples_base_path)
    if not control_paths or not disease_paths:
        print("Error: healthy_csv and disease_csv must each contain at least one sample.", file=sys.stderr)
        sys.exit(1)

    base_project = Path(config.base_project)
    if not base_project.is_file():
        print(f"Error: base_project not found: {base_project}", file=sys.stderr)
        sys.exit(1)

    # Optional: base project has multiple disease groups -> use --per-cancer-group (we generate single comparison, so no)
    per_cancer_group = False

    use_tqdm = sys.stderr.isatty()
    pbar_iter = tqdm(
        total=config.n_iterations,
        desc="Iterations",
        position=0,
        leave=True,
        file=sys.stderr,
        disable=not use_tqdm,
    )

    rows: List[Dict[str, Any]] = []
    all_timings: List[Dict[str, Any]] = []
    for i in range(config.n_iterations):
        run_id = f"run_{i + 1:04d}"
        run_dir = output_base / run_id
        seed_i = (config.seed + i) if config.seed is not None else None

        if use_tqdm:
            step_bar = tqdm(
                total=4,
                desc="Steps",
                position=1,
                leave=False,
                file=sys.stderr,
            )
            step_bar_current: List[Any] = [None]

            def progress_cb(step_index: int, step_name: str, event: str) -> None:
                if event == "start":
                    step_bar.set_description(f"Steps ({step_name})")
                    step_bar_current[0] = tqdm(
                        total=None,
                        desc=f"Running {step_name}...",
                        position=2,
                        leave=False,
                        file=sys.stderr,
                        bar_format="{desc}",
                    )
                else:
                    step_bar.update(1)
                    if step_bar_current[0] is not None:
                        step_bar_current[0].close()
                        step_bar_current[0] = None

            progress_callback = progress_cb
        else:
            progress_callback = None

        try:
            train_control, train_disease, val_control, val_disease = stratified_split(
                control_paths,
                disease_paths,
                config.train_fraction,
                seed=seed_i,
            )
        except ValueError as e:
            print(f"Warning: iteration {i + 1} skipped: {e}", file=sys.stderr)
            if use_tqdm:
                step_bar.close()
            pbar_iter.update(1)
            continue

        project_path, _, _, val_control_csv, val_disease_csv = generate_run_project(
            base_project,
            run_dir,
            run_id,
            config.output_base,
            train_control,
            train_disease,
            val_control,
            val_disease,
            config.samples_base_path,
        )
        validator_output_dir = run_dir / "validator"
        logs_dir = run_dir / "logs"
        n_train_samples = len(train_control) + len(train_disease)
        n_val_samples = len(val_control) + len(val_disease)

        success, errors, step_timings = run_pipeline_for_iteration(
            project_path,
            val_control_csv,
            val_disease_csv,
            validator_output_dir,
            per_cancer_group=per_cancer_group,
            logs_dir=logs_dir,
            progress_callback=progress_callback,
        )
        if use_tqdm:
            step_bar.close()
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
            if use_tqdm:
                step_bar.close()
            if config.abort_on_step_failure:
                print("Aborting (abort_on_step_failure=true).", file=sys.stderr)
                sys.exit(1)
            pbar_iter.update(1)
            continue

        metrics_path = validator_output_dir / "validation_metrics.json"
        if not metrics_path.exists():
            print(f"Warning: {metrics_path} not found after validator run; skipping metrics for {run_id}.", file=sys.stderr)
            if use_tqdm:
                step_bar.close()
            pbar_iter.update(1)
            continue
        metrics = load_metrics_from_json(metrics_path)
        scalar = _scalar_metrics_from_dict(metrics)
        row = {"iteration": i + 1, "run_id": run_id, "run_dir": str(run_dir), **scalar}
        rows.append(row)
        if not use_tqdm:
            print(f"Completed iteration {i + 1}/{config.n_iterations} ({run_id})", file=sys.stderr)
        pbar_iter.update(1)

    if not rows:
        print("No successful iterations; nothing to aggregate.", file=sys.stderr)
        sys.exit(1)

    df = build_metrics_table(rows)
    all_metrics_csv = output_base / "all_metrics.csv"
    write_all_metrics_csv(df, all_metrics_csv)
    print(f"Wrote {all_metrics_csv}")

    summary = compute_summary(df)
    summary_path = output_base / "metrics_summary.json"
    write_summary_json(summary, summary_path)
    print(f"Wrote {summary_path}")

    if all_timings:
        step_timings_path = output_base / "step_timings.csv"
        write_step_timings_csv(all_timings, step_timings_path)
        print(f"Wrote {step_timings_path}")

    print("Done.")


if __name__ == "__main__":
    main()
