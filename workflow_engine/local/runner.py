#!/usr/bin/env python3
"""CLI: run a DomainProgram or compiled WorkflowDefinitionSpec locally."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for rel in ("workflow_engine/local", "workflow_engine/domain", "workflow_engine/contract", "workers"):
    p = REPO_ROOT / rel
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from local.engine import LocalWorkflowEngine
from local.scheduler import SchedulerConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--program", type=Path, help="DomainProgram JSON path")
    src.add_argument("--workflow", type=Path, help="Compiled WorkflowDefinitionSpec JSON path")
    parser.add_argument(
        "--context",
        type=str,
        default=None,
        help="Instance context_json as inline JSON string",
    )
    parser.add_argument("--context-file", type=Path, default=None, help="context_json file")
    parser.add_argument("--dry-run", action="store_true", help="Resolve templates only; do not execute")
    parser.add_argument(
        "--parallel-workers",
        type=int,
        default=1,
        help="Thread pool size for PARALLEL / parallel FOREACH (use 1 on NFS/GPU to avoid lock/OOM races)",
    )
    parser.add_argument(
        "--stub-external",
        action="store_true",
        help="Set WORKER_STUB_EXTERNAL=1 for sample-prep external capabilities",
    )
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Disable signature-based action skip and re-execute all actions",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.stub_external:
        os.environ["WORKER_STUB_EXTERNAL"] = "1"

    # NFS / shared mounts (e.g. /work): avoid HDF5 file-lock failures during parallel centroids.
    os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

    context: dict = {}
    if args.context_file:
        context = json.loads(args.context_file.read_text(encoding="utf-8"))
    if args.context:
        context.update(json.loads(args.context))

    if args.force_rerun:
        context["forceRerun"] = True

    config = SchedulerConfig(
        dry_run=args.dry_run,
        parallel_workers=args.parallel_workers,
        force_rerun=args.force_rerun,
    )
    engine = LocalWorkflowEngine(config=config)

    if args.program:
        result = engine.run_program(args.program, context)
    else:
        spec = LocalWorkflowEngine.load_spec(args.workflow)
        result = engine.run_spec(spec, context)

    print(
        json.dumps(
            {
                "status": result.status,
                "actions": result.trace.executed_actions,
                "skipped_actions": result.trace.skipped_actions,
            },
            indent=2,
        )
    )
    if result.error:
        print(f"error: {result.error}", file=sys.stderr)
        return 1
    return 0 if result.status == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
