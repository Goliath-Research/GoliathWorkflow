"""
Subcommands: plan-runs, run-task, export-queue, aggregate-results.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, List, Optional

from .aggregator import aggregate_discovery_monte_carlo
from .executor import execute_discovery_task
from .mc_config_load import (
    apply_monte_carlo_config_overrides,
    ensure_monte_carlo_output_tree,
    load_monte_carlo_config,
)
from .planner import plan_discovery_runs
from .queue_export import export_queue_artifacts


def _add_common_config_args(
    p: argparse.ArgumentParser,
    *,
    with_stability: bool = True,
) -> None:
    p.add_argument("--config", "-c", type=Path, default=None, help="Monte Carlo config JSON.")
    p.add_argument("--project", "-p", type=Path, default=None, help="Project JSON with step_config.validation.")
    p.add_argument("--iterations", "-n", type=int, default=None, help="Override n_iterations.")
    p.add_argument("--seed", type=int, default=None, help="Override seed.")
    p.add_argument("--output-base", type=Path, default=None, help="Override output_base.")
    p.add_argument("--samples-base-path", type=Path, default=None, help="Override samples_base_path.")
    p.add_argument(
        "--path-remap",
        action="append",
        default=None,
        metavar="OLD=NEW",
        help="Path prefix remap (repeatable).",
    )
    if with_stability:
        p.add_argument(
            "--stability",
            action="store_true",
            help="(aggregate-results) run stability after metrics; (plan) pass-through for featurecut overrides with --stability-featurecuts",
        )
        p.add_argument("--stability-featurecuts", action="store_true", help="FeatureCuts / detector overrides for planning.")
        p.add_argument("--stability-target-ba", type=float, default=None)
        p.add_argument("--stability-min-selected-dmps", type=int, default=None)
    p.add_argument("--skip-enricher", action="store_true", help="(config) skip enricher in downstream runs.")
    p.add_argument("--predictor-only", action="store_true", help="Plan/run predictor-only iterations.")
    p.add_argument("--model-backend", choices=["ecdf", "tabular_sklearn", "generative_hybrid"], default=None)
    p.add_argument("--post-model-backend", choices=["ecdf", "tabular_sklearn", "generative_hybrid"], default=None)
    p.add_argument("--covariates-path", type=Path, default=None)
    p.add_argument("--tabular-max-dmps", type=int, default=None)
    p.add_argument(
        "--tabular-model-type",
        choices=["random_forest", "hist_gradient_boosting", "logistic_regression"],
        default=None,
    )
    p.add_argument("--tabular-methods-json", type=str, default=None)
    p.add_argument("--generative-epochs", type=int, default=None)
    p.add_argument("--generative-batch-size", type=int, default=None)
    p.add_argument("--no-generative-covariates-strict", action="store_true")


def _load_and_apply(args: Any, p: Optional[argparse.ArgumentParser] = None) -> Any:
    ap = p if p is not None else argparse.ArgumentParser()
    config, _ = load_monte_carlo_config(args, ap)
    return apply_monte_carlo_config_overrides(config, args)


def cmd_plan_runs(argv: List[str]) -> None:
    p = argparse.ArgumentParser(description="Pre-generate run folders and per-run task JSON (no heavy pipeline).")
    _add_common_config_args(p)
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete existing run_* and queue/tasks under monte_carlo_runs before planning.",
    )
    ns, rest = p.parse_known_args(argv)
    if rest:
        print(f"Error: unknown args: {rest!r}", file=sys.stderr)
        sys.exit(2)
    if ns.config is None and ns.project is None:
        p.error("Either --config or --project is required")
    config = _load_and_apply(ns, p)
    _base, _bpc, _ob, mcr = ensure_monte_carlo_output_tree(config)
    plan = plan_discovery_runs(
        config=config,
        base_project=Path(config.base_project),
        monte_carlo_runs_root=mcr,
        overwrite=bool(ns.overwrite),
    )
    n = plan.get("n_planned", 0)
    print(f"Planned {n} runs. Tasks under {mcr / 'queue' / 'tasks'}")
    print("Next: methyl-validation export-queue, then run workers: methyl-validation run-task --task <...>")


def cmd_run_task(argv: List[str]) -> None:
    p = argparse.ArgumentParser(description="Execute a single task JSON (worker).")
    p.add_argument("--task", type=Path, required=True, help="Path to queue/tasks/<run_####>.json")
    ns, rest = p.parse_known_args(argv)
    if rest:
        p.error(f"unknown args: {rest!r}")
    if not ns.task.is_file():
        p.error(f"not a file: {ns.task}")
    sys.exit(execute_discovery_task(str(ns.task.resolve())))


def cmd_export_queue(argv: List[str]) -> None:
    p = argparse.ArgumentParser(description="Emit queue_manifest.jsonl and commands.sh for a work queue backend.")
    p.add_argument(
        "--monte-carlo-runs",
        type=Path,
        default=None,
        help=".../project_name/monte_carlo_runs. If omitted, use --config/--project to resolve.",
    )
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--project", type=Path, default=None)
    p.add_argument("--iterations", type=int, default=None)
    p.add_argument("--output-base", type=Path, default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--samples-base-path", type=Path, default=None)
    p.add_argument("--path-remap", action="append", default=None, metavar="OLD=NEW")
    p.add_argument("--stability-featurecuts", action="store_true")
    p.add_argument("--stability-target-ba", type=float, default=None)
    p.add_argument("--stability-min-selected-dmps", type=int, default=None)
    p.add_argument("--skip-enricher", action="store_true")
    p.add_argument("--predictor-only", action="store_true")
    p.add_argument("--model-backend", choices=["ecdf", "tabular_sklearn", "generative_hybrid"], default=None)
    p.add_argument("--post-model-backend", choices=["ecdf", "tabular_sklearn", "generative_hybrid"], default=None)
    p.add_argument("--covariates-path", type=Path, default=None)
    ns, rest = p.parse_known_args(argv)
    if rest:
        p.error(f"unknown args: {rest!r}")
    mroot = ns.monte_carlo_runs
    if mroot is None:
        if ns.config is None and ns.project is None:
            p.error("Provide --monte-carlo-runs or --config/--project")
        config = _load_and_apply(ns, p)
        *_, mroot = ensure_monte_carlo_output_tree(config)
    mroot = Path(mroot)
    if not mroot.is_dir():
        p.error(f"not a directory: {mroot}")
    summ = export_queue_artifacts(mroot)
    print("Wrote:")
    for k, v in summ.items():
        print(f"  {k}: {v}")


def cmd_aggregate_results(argv: List[str]) -> None:
    p = argparse.ArgumentParser(
        description="Regenerate all_metrics and metrics_summary from per-run results (and optional --stability)."
    )
    _add_common_config_args(p)
    p.add_argument(
        "--monte-carlo-runs",
        type=Path,
        default=None,
        help="Explicit monte_carlo_runs directory (overrides --output-base resolution).",
    )
    ns, rest = p.parse_known_args(argv)
    if rest:
        p.error(f"unknown args: {rest!r}")
    if ns.config is None and ns.project is None:
        p.error("Either --config or --project is required")
    config = _load_and_apply(ns, p)
    mcr = ns.monte_carlo_runs
    if mcr is None:
        *_, mcr = ensure_monte_carlo_output_tree(config)
    mcr = Path(mcr)
    if not mcr.is_dir():
        p.error(f"not a directory: {mcr}")
    aggregate_discovery_monte_carlo(
        mcr,
        config,
        run_stability=bool(ns.stability),
    )
    print("Done.")


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        print(
            "Usage: methyl-validation {plan-runs|run-task|export-queue|aggregate-results} [options]\n"
            "  plan-runs      Pre-generate run_#### and queue/task JSONs\n"
            "  run-task        Execute one task JSON (worker)\n"
            "  export-queue   Write queue_manifest.jsonl and commands.sh\n"
            "  aggregate-results  Merge metrics + optional --stability",
            file=sys.stderr,
        )
        sys.exit(2)
    if argv[0] in ("-h", "--help", "help"):
        print(
            "Subcommands: plan-runs, run-task, export-queue, aggregate-results\n"
            "  methyl-validation plan-runs --config FILE [--overwrite]\n"
            "  methyl-validation run-task --task queue/tasks/run_0001.json\n"
            "  methyl-validation export-queue --monte-carlo-runs PATH  # or use --config\n"
            "  methyl-validation aggregate-results --config FILE [--stability]\n"
        )
        sys.exit(0)
    sub = argv[0]
    rest = argv[1:]
    if sub == "plan-runs":
        cmd_plan_runs(rest)
    elif sub == "run-task":
        cmd_run_task(rest)
    elif sub == "export-queue":
        cmd_export_queue(rest)
    elif sub == "aggregate-results":
        cmd_aggregate_results(rest)
    else:
        print(f"Error: unknown subcommand {sub!r}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
