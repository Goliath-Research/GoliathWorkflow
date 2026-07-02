#!/usr/bin/env python3
"""Rewrite Monte Carlo config snapshots without deprecated legacy backend keys.

Existing ``monte_carlo_runs/queue/mc_config.json`` snapshots were written by older
code and carry flat legacy backend keys (model_backend, tabular_methods,
mapper_gene_columns, …). The current strict ``MonteCarloConfig`` rejects those keys
on input, so stale snapshots either fail to load or keep re-seeding deprecated values.

This one-way migration loads each snapshot, moves any legacy keys into
``backend_profiles`` (via the shared migrator), validates, and rewrites the file
with the canonical clean serializer (deprecated keys omitted).

Usage:
  scripts/migrate_mc_config_snapshots.py <root> [<root> ...] [--dry-run] [--no-backup]

  <root> may be a single mc_config.json, a monte_carlo_runs dir, or any parent dir
  to scan recursively for **/queue/mc_config.json and **/mc_config.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[1]
for rel in ("packages/methylvalidation", "packages/methylutils", "packages/methyldomain"):
    p = REPO_ROOT / rel
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _iter_snapshots(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    if not root.is_dir():
        return
    seen: set[Path] = set()
    for pattern in ("**/queue/mc_config.json", "**/mc_config.json"):
        for path in root.glob(pattern):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path


def _migrate_one(path: Path, *, dry_run: bool, backup: bool) -> str:
    from methyl_validation.config import MonteCarloConfig
    from methyl_validation.utils.migrate_backend_config import (
        LEGACY_BACKEND_KEYS,
        merge_legacy_validation_keys_into_backend_profiles,
    )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"SKIP  {path} (unreadable: {exc})"
    if not isinstance(raw, dict):
        return f"SKIP  {path} (not a JSON object)"

    legacy_present = sorted(k for k in raw if k in LEGACY_BACKEND_KEYS)
    if legacy_present:
        raw, _ = merge_legacy_validation_keys_into_backend_profiles(raw)

    try:
        config = MonteCarloConfig.model_validate(raw)
    except Exception as exc:
        return f"FAIL  {path} (validation error after migration: {str(exc).splitlines()[0]})"

    clean = config.dump_clean_json(indent=2)
    if clean.strip() == path.read_text(encoding="utf-8").strip():
        return f"OK    {path} (already clean)"

    if dry_run:
        return f"WOULD {path} (drop {len(legacy_present)} legacy keys)"

    if backup:
        backup_path = path.with_suffix(path.suffix + ".legacy.bak")
        if not backup_path.exists():
            backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(clean + "\n", encoding="utf-8")
    return f"WROTE {path} (dropped {len(legacy_present)} legacy keys)"


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", nargs="+", help="mc_config.json file(s) or director(ies) to scan")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    parser.add_argument("--no-backup", action="store_true", help="Do not write a .legacy.bak copy")
    args = parser.parse_args(argv)

    snapshots: List[Path] = []
    for root in args.roots:
        snapshots.extend(_iter_snapshots(Path(root).expanduser()))
    if not snapshots:
        print("No mc_config.json snapshots found.", file=sys.stderr)
        return 1

    changed = 0
    failed = 0
    for path in snapshots:
        result = _migrate_one(path, dry_run=args.dry_run, backup=not args.no_backup)
        print(result)
        if result.startswith(("WROTE", "WOULD")):
            changed += 1
        elif result.startswith("FAIL"):
            failed += 1

    print(f"\n{len(snapshots)} snapshot(s); {changed} to change; {failed} failed.", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
