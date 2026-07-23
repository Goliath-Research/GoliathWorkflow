#!/usr/bin/env python3
"""Fail when catalog actions lack task schemas or committed golden I/O fixtures.

Lightweight companion to pytest workers/tests/test_golden_task_outputs.py and
methyl-export-action-catalog --check — runnable without a full editable install.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG = REPO_ROOT / "schemas" / "actions" / "catalog.json"
GOLDEN_DIR = REPO_ROOT / "workers" / "tests" / "golden"
GOLDEN_DATA = REPO_ROOT / "workers" / "tests" / "golden_fixtures_data.py"


def _golden_stem(action_name: str) -> str:
    return action_name.replace(".", "_")


def _load_catalog_actions(catalog_path: Path = CATALOG) -> list[dict]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    actions = payload.get("actions", payload)
    if not isinstance(actions, list):
        raise ValueError(f"unexpected catalog shape in {catalog_path}")
    return [a for a in actions if isinstance(a, dict) and a.get("action_name")]


def _golden_data_mentions(action_name: str, text: str) -> bool:
    # Match dict keys in golden_fixtures_data.py
    return f'"{action_name}"' in text


def check_catalog_fixture_contract(root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    catalog_path = root / "schemas" / "actions" / "catalog.json"
    golden_dir = root / "workers" / "tests" / "golden"
    golden_data_path = root / "workers" / "tests" / "golden_fixtures_data.py"

    if not catalog_path.is_file():
        return [f"missing catalog: {catalog_path.relative_to(root)}"]
    if not golden_data_path.is_file():
        return [f"missing golden data module: {golden_data_path.relative_to(root)}"]

    golden_data_text = golden_data_path.read_text(encoding="utf-8")
    actions = _load_catalog_actions(catalog_path)

    for action in actions:
        name = str(action["action_name"])
        for key in ("input_schema_ref", "output_schema_ref"):
            ref = action.get(key)
            if not ref:
                errors.append(f"{name}: missing {key} in catalog")
                continue
            ref_path = root / str(ref)
            if not ref_path.is_file():
                errors.append(f"{name}: missing schema file {ref}")

        stem = _golden_stem(name)
        for direction in ("input", "output"):
            golden_path = golden_dir / f"{stem}.{direction}.json"
            if not golden_path.is_file():
                errors.append(
                    f"{name}: missing golden {direction} "
                    f"{golden_path.relative_to(root)} "
                    f"(update golden_fixtures_data.py + scripts/generate_golden_fixtures.py)"
                )

        if not _golden_data_mentions(name, golden_data_text):
            errors.append(
                f"{name}: not referenced in workers/tests/golden_fixtures_data.py"
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    del argv
    errors = check_catalog_fixture_contract()
    if not errors:
        print(f"Catalog fixture contract OK ({len(_load_catalog_actions())} actions).")
        return 0
    print("Catalog fixture contract violations:", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
