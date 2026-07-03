#!/usr/bin/env python3
"""
Admin-tier study lifecycle CLI (domain-aware).

Compiles DomainPrograms, plans instance context, bakes resolvedConfig scope vars,
and creates/starts workflow instances via the agnostic gateway DB layer or admin HTTP API.

This replaces domain-specific routes formerly hosted on methyl-gateway.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from admin._paths import ensure_import_paths


def _load_body(path: Optional[str]) -> Dict[str, Any]:
    if path is None or path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    return json.loads(raw) if raw.strip() else {}


def _open_db():
    from rest.connection import resolve_connection_config
    from rest.db import open_gateway_db

    return open_gateway_db(resolve_connection_config())


def cmd_compile(args: argparse.Namespace) -> int:
    from admin.study_lifecycle import compile_program_spec

    program = Path(args.program).expanduser().resolve()
    spec = compile_program_spec(program, project_path=args.project_path)
    if args.output:
        Path(args.output).write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    else:
        json.dump({"spec": spec}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


def cmd_validation_start(args: argparse.Namespace) -> int:
    from rest.db_client import (
        create_workflow_definition,
        create_workflow_instance,
        start_workflow_instance,
    )
    from admin.study_lifecycle import start_study_validation

    body = _load_body(args.body_file)
    if args.project_path:
        body["projectPath"] = args.project_path
    if args.program_path:
        body["program_path"] = args.program_path
    if args.workflow_version_id is not None:
        body["workflow_version_id"] = args.workflow_version_id

    db = _open_db()
    try:
        payload = start_study_validation(
            db,
            body,
            create_workflow_definition=create_workflow_definition,
            create_workflow_instance=create_workflow_instance,
            start_workflow_instance=start_workflow_instance,
        )
    finally:
        db.close()

    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_sample_prep_start(args: argparse.Namespace) -> int:
    from rest.db_client import (
        create_workflow_definition,
        create_workflow_instance,
        start_workflow_instance,
    )
    from admin.sample_lifecycle import start_sample_prep

    body = _load_body(args.body_file)
    if args.project_path:
        body["projectPath"] = args.project_path
    if args.workflow_version_id is not None:
        body["workflow_version_id"] = args.workflow_version_id

    db = _open_db()
    try:
        payload = start_sample_prep(
            db,
            body,
            create_workflow_definition=create_workflow_definition,
            create_workflow_instance=create_workflow_instance,
            start_workflow_instance=start_workflow_instance,
        )
    finally:
        db.close()

    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_plan_iterations(args: argparse.Namespace) -> int:
    from methyl_validation.workflow_planner import plan_validation_context
    from rest.db_client import apply_validation_plan
    from workflow_context import finalize_instance_context

    body = _load_body(args.body_file)
    planned = plan_validation_context(body)
    context = finalize_instance_context(planned.model_dump(mode="json"))

    if args.workflow_instance_id is not None:
        db = _open_db()
        try:
            apply_validation_plan(
                db,
                int(args.workflow_instance_id),
                context,
                persist_extension=not args.no_persist_extension,
            )
        finally:
            db.close()

    json.dump(
        {
            "context_json": context,
            "n_iterations": len(context.get("iterations", [])),
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ensure_import_paths()

    parser = argparse.ArgumentParser(
        description="MethylPipeline admin study lifecycle (compile, plan, start instances)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_compile = sub.add_parser("compile", help="Compile a DomainProgram to WorkflowDefinitionSpec JSON")
    p_compile.add_argument("program", help="Path to *.program.json")
    p_compile.add_argument("--project-path", dest="project_path", default=None)
    p_compile.add_argument("-o", "--output", default=None, help="Write spec JSON to file")
    p_compile.set_defaults(func=cmd_compile)

    p_val = sub.add_parser("validation-start", help="Plan and start a study validation workflow")
    p_val.add_argument(
        "body_file",
        nargs="?",
        default="-",
        help="JSON request body (default: stdin)",
    )
    p_val.add_argument("--project-path", dest="project_path", default=None)
    p_val.add_argument("--program-path", dest="program_path", default=None)
    p_val.add_argument("--workflow-version-id", type=int, default=None)
    p_val.set_defaults(func=cmd_validation_start)

    p_prep = sub.add_parser("sample-prep-start", help="Plan and start SamplePrepPipeline")
    p_prep.add_argument(
        "body_file",
        nargs="?",
        default="-",
        help="JSON request body (default: stdin)",
    )
    p_prep.add_argument("--project-path", dest="project_path", default=None)
    p_prep.add_argument("--workflow-version-id", type=int, default=None)
    p_prep.set_defaults(func=cmd_sample_prep_start)

    p_plan = sub.add_parser("plan-iterations", help="Plan validation iterations context JSON")
    p_plan.add_argument(
        "body_file",
        nargs="?",
        default="-",
        help="JSON planner payload (default: stdin)",
    )
    p_plan.add_argument("--workflow-instance-id", type=int, default=None)
    p_plan.add_argument("--no-persist-extension", action="store_true")
    p_plan.set_defaults(func=cmd_plan_iterations)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
