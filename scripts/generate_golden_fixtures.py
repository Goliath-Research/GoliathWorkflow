#!/usr/bin/env python3
"""Write workers/tests/golden/*.json from golden_fixtures_data (validated against catalog models)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "workers"))
sys.path.insert(0, str(REPO / "workers" / "tests"))

from golden_fixtures_data import GOLDEN_INPUTS, GOLDEN_OUTPUTS
from methyl_worker.task_schema_registry import list_task_schema_specs


def _filename(action_name: str, direction: str) -> str:
    safe = action_name.replace(".", "_")
    return f"{safe}.{direction}.json"


def main() -> int:
    out_dir = REPO / "workers" / "tests" / "golden"
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = list_task_schema_specs()
    missing_in: list[str] = []
    missing_out: list[str] = []
    for spec in specs:
        name = spec.action_name
        if name not in GOLDEN_INPUTS:
            missing_in.append(name)
        else:
            payload = spec.load_input_model().model_validate(GOLDEN_INPUTS[name]).model_dump(mode="json")
            (out_dir / _filename(name, "input")).write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        if name not in GOLDEN_OUTPUTS:
            missing_out.append(name)
        else:
            payload = spec.load_output_model().model_validate(GOLDEN_OUTPUTS[name]).model_dump(mode="json")
            (out_dir / _filename(name, "output")).write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    if missing_in or missing_out:
        if missing_in:
            print("Missing GOLDEN_INPUTS:", ", ".join(missing_in), file=sys.stderr)
        if missing_out:
            print("Missing GOLDEN_OUTPUTS:", ", ".join(missing_out), file=sys.stderr)
        return 1
    print(f"Wrote {len(specs) * 2} golden fixtures to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
