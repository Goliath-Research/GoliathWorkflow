#!/usr/bin/env python3
"""Plan and start SamplePrep or StudyValidation instances via direct DB.

Replaces the former ``methyl-study-start`` admin CLI. Production operators use
portal SQL (``portal.sp_create_and_start_instance``); this script is for CI/smoke.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
WF_ENGINE = REPO_ROOT / "workflow_engine"
sys.path.insert(0, str(WF_ENGINE))


def _load_body(path: str) -> dict[str, Any]:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("sample-prep-start", "validation-start", "compile"),
        help="Lifecycle operation",
    )
    parser.add_argument(
        "request",
        nargs="?",
        default="-",
        help="JSON request path or '-' for stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write compile result to this path (compile only)",
    )
    args = parser.parse_args(argv)

    if args.command == "compile":
        from ops.study_lifecycle import compile_program_spec

        body = _load_body(args.request) if args.request != "-" or not sys.stdin.isatty() else {}
        program = body.get("program_path") or args.request
        if program == "-":
            raise SystemExit("compile requires program_path in JSON or as request path")
        project_path = body.get("projectPath") if isinstance(body, dict) else None
        spec = compile_program_spec(Path(program), project_path=project_path)
        text = json.dumps(spec, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0

    from rest.connection import resolve_connection_config
    from rest.db import open_gateway_db
    from rest.db_client import (
        create_workflow_definition,
        create_workflow_instance,
        start_workflow_instance,
    )

    body = _load_body(args.request)
    config = resolve_connection_config()
    db = open_gateway_db(config)
    try:
        if args.command == "validation-start":
            from ops.study_lifecycle import start_study_validation

            result = start_study_validation(
                db,
                body,
                create_workflow_definition=create_workflow_definition,
                create_workflow_instance=create_workflow_instance,
                start_workflow_instance=start_workflow_instance,
            )
        else:
            from ops.sample_lifecycle import start_sample_prep

            result = start_sample_prep(
                db,
                body,
                create_workflow_definition=create_workflow_definition,
                create_workflow_instance=create_workflow_instance,
                start_workflow_instance=start_workflow_instance,
            )
        db.commit()
    finally:
        db.close()

    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
