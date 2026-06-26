#!/usr/bin/env python3
"""Remove legacy step_config from Monte Carlo run project.json files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def strip_run_projects(root: Path, *, dry_run: bool = False) -> int:
    changed = 0
    for project_path in sorted(root.glob("run_*/project.json")):
        data = json.loads(project_path.read_text(encoding="utf-8"))
        if "step_config" not in data:
            continue
        changed += 1
        if dry_run:
            print(f"would strip step_config: {project_path}")
            continue
        data.pop("step_config", None)
        project_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"stripped step_config: {project_path}")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "monte_carlo_runs_root",
        type=Path,
        help="Path to .../monte_carlo_runs (contains run_0001/, run_0002/, ...)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    root = args.monte_carlo_runs_root.expanduser().resolve()
    if not root.is_dir():
        print(f"Error: not a directory: {root}", file=sys.stderr)
        return 2
    n = strip_run_projects(root, dry_run=args.dry_run)
    print(f"{'Would update' if args.dry_run else 'Updated'} {n} run project.json file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
