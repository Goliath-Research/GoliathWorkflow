"""
CLI for methyl-disease-progression.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .progression import run_progression_report


def _parse_labels(raw: Optional[str]) -> Optional[List[str]]:
    if raw is None:
        return None
    tokens = [x.strip() for x in raw.split(",") if x.strip()]
    return tokens or None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Synthesize cross-stage disease progression tables from per-comparison "
            "MethylMapper and MethylEnricher outputs."
        )
    )
    parser.add_argument("--project", type=Path, required=True, help="Path to project JSON.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory (default: <project_root>/progression).",
    )
    parser.add_argument(
        "--ordered-comparison-labels",
        type=str,
        default=None,
        help="Optional comma-separated explicit stage order using comparison_label and/or disease_group.",
    )
    parser.add_argument(
        "--strict-missing",
        action="store_true",
        help="Fail when any expected stage input file is missing.",
    )
    parser.add_argument(
        "--report-md",
        action="store_true",
        help="Write an additional markdown summary report.md.",
    )
    args = parser.parse_args()

    try:
        summary = run_progression_report(
            project_path=args.project,
            output_dir=args.output_dir,
            ordered_comparison_labels=_parse_labels(args.ordered_comparison_labels),
            strict_missing=bool(args.strict_missing),
            report_md=bool(args.report_md),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("Disease progression report complete.")
    print(f"Output directory: {summary.get('output_dir')}")
    print(f"Summary JSON: {summary.get('summary_json')}")


if __name__ == "__main__":
    main()

