#!/usr/bin/env python3
"""Fail if any committed project*.json still contains a step_config key."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Paths relative to repo root that may contain legacy step_config fixtures.
EXCLUDE_DIR_PREFIXES = (
    ".git/",
    ".venv/",
    "__pycache__/",
    "node_modules/",
)

EXCLUDE_FILE_SUFFIXES = (
    ".legacy.bak",
)


def _is_excluded(rel: str) -> bool:
    if any(rel.startswith(prefix) for prefix in EXCLUDE_DIR_PREFIXES):
        return True
    if rel.endswith(EXCLUDE_FILE_SUFFIXES):
        return True
    # Migration script tests may use synthetic legacy payloads outside project*.json.
    if rel.startswith("scripts/tests/test_migrate_project_config"):
        return True
    return False


def find_project_files_with_step_config(root: Path = REPO_ROOT) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for path in sorted(root.rglob("project*.json")):
        rel = path.relative_to(root).as_posix()
        if _is_excluded(rel):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            violations.append((rel, f"invalid JSON: {exc}"))
            continue
        if isinstance(payload, dict) and "step_config" in payload:
            violations.append((rel, "contains forbidden top-level key 'step_config'"))
    return violations


def main(argv: list[str] | None = None) -> int:
    del argv
    violations = find_project_files_with_step_config()
    if not violations:
        return 0
    print("Committed project*.json files must not contain step_config:", file=sys.stderr)
    for rel, reason in violations:
        print(f"  {rel}: {reason}", file=sys.stderr)
    print(
        "\nMigrate with scripts/migrate_project_config.py and move tool params to "
        "profile actionConfig + site manifest.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
