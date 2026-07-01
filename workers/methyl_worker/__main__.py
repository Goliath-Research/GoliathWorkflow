"""CLI entry point: python -m methyl_worker or methyl-worker."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .capabilities import assert_node_can_serve_capability
from .client import WorkflowRestClient
from .runner import WorkerRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MethylPipeline REST workflow worker (poll middle-tier API)",
    )
    parser.add_argument("--worker-id", type=int, default=int(os.environ.get("WORKER_ID", "0")))
    parser.add_argument("--worker-token", default=os.environ.get("WORKER_TOKEN", ""))
    parser.add_argument("--capability", default=os.environ.get("WORKER_CAPABILITY"))
    parser.add_argument(
        "--api-base",
        default=os.environ.get("METHYL_API_BASE", "http://localhost:8080/v1"),
        help="Middle-tier base URL (default: METHYL_API_BASE or http://localhost:8080/v1)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=float(os.environ.get("WORKER_POLL_SECONDS", "5")),
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=float(os.environ.get("WORKER_HEARTBEAT_SECONDS", "60")),
    )
    parser.add_argument("--once", action="store_true", help="Poll once then exit")
    parser.add_argument(
        "--authenticate",
        action="store_true",
        help="Call POST /workers/authenticate before polling",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="poll",
        choices=("poll", "plan-iterations"),
        help="poll (default): workflow task loop; plan-iterations: Monte Carlo planner CLI",
    )
    parser.add_argument(
        "--plan-input",
        help="JSON file for plan-iterations command (default: stdin or minimal from flags)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.command == "plan-iterations":
        return _run_plan_iterations_cli(args)

    if args.worker_id <= 0 or not args.worker_token:
        parser.error("Set --worker-id and --worker-token (or WORKER_ID / WORKER_TOKEN env vars)")

    if args.capability:
        assert_node_can_serve_capability(args.capability)

    client = WorkflowRestClient(args.api_base)
    if args.authenticate:
        client.authenticate(args.worker_id, args.worker_token)

    if args.once:
        claim = client.request_task(args.worker_id, args.worker_token, args.capability)
        print(json.dumps({"has_task": claim is not None, "claim": _claim_dict(claim)}, indent=2))
        return 0

    runner = WorkerRunner(
        client,
        args.worker_id,
        args.worker_token,
        args.capability,
        poll_seconds=args.poll_seconds,
        heartbeat_seconds=args.heartbeat_seconds,
    )
    runner.run_forever()
    return 0


def _claim_dict(claim) -> dict | None:
    if claim is None:
        return None
    return {
        "node_execution_id": claim.node_execution_id,
        "workflow_instance_id": claim.workflow_instance_id,
        "action_name": claim.action_name,
        "capability": claim.capability,
        "node_key": claim.node_key,
        "input_json": claim.input_json,
    }


def _run_plan_iterations_cli(args: argparse.Namespace) -> int:
    from methyl_validation.workflow_planner import plan_validation_context

    if args.plan_input:
        payload = json.loads(Path(args.plan_input).read_text(encoding="utf-8"))
    else:
        payload = {"projectPath": os.environ.get("PROJECT_PATH", "")}
        if not payload["projectPath"]:
            print("Set PROJECT_PATH or pass --plan-input", file=sys.stderr)
            return 2
    context = plan_validation_context(payload)
    print(json.dumps(context.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
