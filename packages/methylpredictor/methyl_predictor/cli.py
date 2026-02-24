"""
Command-line interface for MethylPredictor.
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Optional

from .core.predictor import run_prediction
from .models.config import PredictorConfig
from .project_resolver import (
    resolve_predictor_config,
    resolve_predictor_config_per_comparison,
)

try:
    from methyl_utils import load_project
except ImportError:
    load_project = None


def _read_paths_from_csv(csv_path: Path) -> List[str]:
    """Read sample directory paths from a CSV (one column or column named 'path'/'sample')."""
    paths = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            # Prefer column named 'path' or 'sample' or first column
            key = None
            for name in ("path", "sample", "sample_path"):
                if name in (reader.fieldnames or []):
                    key = name
                    break
            if key is None:
                key = reader.fieldnames[0]
            for row in reader:
                p = row.get(key, "").strip()
                if p:
                    paths.append(p)
        else:
            for row in reader:
                for v in row.values():
                    if v and v.strip():
                        paths.append(v.strip())
                        break
    return paths


def _parse_test_paths_arg(arg: Optional[str]) -> Optional[List[str]]:
    """Parse --test-control or --test-disease: comma-separated paths or a single CSV path."""
    if not arg or not arg.strip():
        return None
    s = arg.strip()
    path = Path(s)
    if path.suffix.lower() in (".csv", ".txt") and path.exists():
        if path.suffix.lower() == ".csv":
            return _read_paths_from_csv(path)
        with open(path) as f:
            return [line.strip() for line in f if line.strip()]
    # Comma-separated list
    return [p.strip() for p in s.split(",") if p.strip()]


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MethylPredictor - Run MethylClassifier on test sample sets and compute metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From project; uses default test set from step_config.predictor if defined
  methyl-predictor --project project.json

  # Override test set on the command line
  methyl-predictor --project project.json --test-control control.csv --test-disease disease.csv

  # Override output and step config
  methyl-predictor --project project.json --output-dir ./out --step-override overrides.json

  # Standalone (no project): model dir + output + test sets
  methyl-predictor --model-dir /path/to/classifiers/healthy/cancer --output-dir ./out \\
    --test-control control.csv --test-disease disease.csv
        """,
    )
    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        metavar="JSON",
        help="Path to pipeline project config. Default test set is taken from step_config.predictor "
        "(test_control_paths, test_disease_paths) unless overridden by --test-control/--test-disease.",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        metavar="JSON",
        help="Path to predictor config JSON (alternative to --project; must include model_path/model_dir, output_dir, test_control_paths, test_disease_paths).",
    )
    parser.add_argument(
        "--model",
        type=Path,
        metavar="PKL",
        help="Path to single classifier .pkl file (overrides project/config).",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        metavar="DIR",
        help="Path to directory with classifier-{chrom}.pkl files (overrides project/config).",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        metavar="DIR",
        help="Output directory for validation_metrics.json and predictions CSV.",
    )
    parser.add_argument(
        "--step-override",
        type=Path,
        metavar="JSON",
        help="Optional JSON overrides for predictor/classifier step (when using --project).",
    )
    parser.add_argument(
        "--test-control",
        metavar="CSV_OR_PATHS",
        help="Override control test set (overrides step_config.predictor): CSV path or comma-separated paths.",
    )
    parser.add_argument(
        "--test-disease",
        metavar="CSV_OR_PATHS",
        help="Override disease test set (overrides step_config.predictor): CSV path or comma-separated paths.",
    )
    parser.add_argument(
        "--per-comparison",
        action="store_true",
        help="With --project: run one run per comparison. Auto-enabled when project uses controls/diseases.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output.",
    )
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    # Config file mode (no project)
    if args.config is not None:
        import json
        with open(args.config) as f:
            data = json.load(f)
        if args.model is not None:
            data["model_path"] = str(args.model)
            data["model_dir"] = None
        if args.model_dir is not None:
            data["model_dir"] = str(args.model_dir)
            data["model_path"] = None
        if args.output_dir is not None:
            data["output_dir"] = str(args.output_dir)
        if args.test_control is not None:
            data["test_control_paths"] = _parse_test_paths_arg(args.test_control) or []
            print(f"Test control paths: {data['test_control_paths']}")
        if args.test_disease is not None:
            data["test_disease_paths"] = _parse_test_paths_arg(args.test_disease) or []
            print(f"Test disease paths: {data['test_disease_paths']}")
        data["debug"] = data.get("debug", False) or args.debug
        config = PredictorConfig(**data)
        run_prediction(config)
        return

    # Project mode
    if args.project is not None:
        test_control = _parse_test_paths_arg(args.test_control)
        test_disease = _parse_test_paths_arg(args.test_disease)
        output_dir = str(args.output_dir) if args.output_dir is not None else None

        use_per_comparison = getattr(args, "per_comparison", False)
        if load_project is not None:
            project = load_project(args.project)
            if getattr(project, "uses_control_disease", lambda: False)():
                use_per_comparison = True

        if use_per_comparison:
            configs = resolve_predictor_config_per_comparison(
                args.project,
                step_override_path=args.step_override,
                test_control_paths=test_control,
                test_disease_paths=test_disease,
            )
            for cfg, label in configs:
                if args.model is not None:
                    cfg.model_path = str(args.model)
                    cfg.model_dir = None
                if args.model_dir is not None:
                    cfg.model_dir = str(args.model_dir)
                    cfg.model_path = None
                cfg.debug = cfg.debug or args.debug
                print(f"\n🔬 Prediction run: {label}")
                run_prediction(cfg)
            return

        config = resolve_predictor_config(
            args.project,
            step_override_path=args.step_override,
            output_dir=output_dir,
            test_control_paths=test_control,
            test_disease_paths=test_disease,
        )
        if args.model is not None:
            config.model_path = str(args.model)
            config.model_dir = None
        if args.model_dir is not None:
            config.model_dir = str(args.model_dir)
            config.model_path = None
        config.debug = config.debug or args.debug
        run_prediction(config)
        return

    # Standalone: require model (or model_dir), output-dir, test-control, test-disease
    if args.model is None and args.model_dir is None:
        parser.error("Without --project or --config, provide --model or --model-dir")
    if args.output_dir is None:
        parser.error("Without --project or --config, provide --output-dir")
    if args.test_control is None or args.test_disease is None:
        parser.error("Without --project or --config, provide --test-control and --test-disease")

    control_paths = _parse_test_paths_arg(args.test_control)
    disease_paths = _parse_test_paths_arg(args.test_disease)
    if not control_paths or not disease_paths:
        print("Error: --test-control and --test-disease must yield at least one path each.", file=sys.stderr)
        sys.exit(1)

    config = PredictorConfig(
        model_path=str(args.model) if args.model is not None else None,
        model_dir=str(args.model_dir) if args.model_dir is not None else None,
        output_dir=str(args.output_dir),
        test_control_paths=control_paths,
        test_disease_paths=disease_paths,
        debug=args.debug,
    )
    run_prediction(config)


if __name__ == "__main__":
    main()
