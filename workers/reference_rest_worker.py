#!/usr/bin/env python3
"""
Reference REST worker for MethylPipeline workflow engine.

Polls the middle-tier REST API (OpenAPI contract) and dispatches to local methyl-* tools.
Database-dialect agnostic — no direct SQL connection.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def _api_base() -> str:
    return os.environ.get("METHYL_API_BASE", "http://localhost:8080/v1").rstrip("/")


def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{_api_base()}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {path}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed {path}: {exc}") from exc


def request_task(worker_id: int, worker_token: str, capability: Optional[str]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "worker_id": worker_id,
        "worker_token": worker_token,
        "max_lease_seconds": int(os.environ.get("WORKER_LEASE_SECONDS", "300")),
    }
    if capability:
        payload["capability"] = capability
    return _post_json("/workers/tasks/request", payload)


def submit_result(
    node_execution_id: int,
    worker_id: int,
    worker_token: str,
    result_code: int,
    output_json: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "worker_id": worker_id,
        "worker_token": worker_token,
        "result_code": result_code,
    }
    if output_json is not None:
        payload["output_json"] = output_json
    return _post_json(f"/workers/tasks/{node_execution_id}/submit", payload)


def heartbeat(node_execution_id: int, worker_id: int, worker_token: str) -> None:
    _post_json(
        f"/workers/tasks/{node_execution_id}/heartbeat",
        {
            "worker_id": worker_id,
            "worker_token": worker_token,
            "extend_seconds": int(os.environ.get("WORKER_LEASE_SECONDS", "300")),
        },
    )


def run_tool(action_name: str, input_json: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch to methyl-* CLI based on action_name or input_json tool hints."""
    tool = input_json.get("workerTool") or action_name
    mapping = {
        "MethylCentroid": "methyl-centroid",
        "MethylDetector": "methyl-detector",
        "MethylMapper": "methyl-mapper",
        "MethylEnricher": "methyl-enricher",
        "MethylDiseaseProgression": "methyl-disease-progression",
    }
    cli = mapping.get(str(tool), str(tool).lower())
    project = input_json.get("projectPath") or input_json.get("project_path")
    if not project:
        return {"status": "skipped", "reason": "no projectPath in input_json"}

    cmd = [cli, "--project", str(project)]
    logger.info("Running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"{cli} failed")
    return {"status": "ok", "stdout_tail": (proc.stdout or "")[-500:]}


def poll_loop(worker_id: int, worker_token: str, capability: Optional[str], poll_seconds: float) -> None:
    while True:
        claim = request_task(worker_id, worker_token, capability)
        if not claim.get("has_task"):
            time.sleep(poll_seconds)
            continue

        ne_id = int(claim["node_execution_id"])
        action = str(claim.get("action_name") or "")
        inp = claim.get("input_json") or {}
        if isinstance(inp, str):
            inp = json.loads(inp) if inp else {}

        try:
            heartbeat(ne_id, worker_id, worker_token)
            out = run_tool(action, inp)
            ack = submit_result(ne_id, worker_id, worker_token, 1, out)
            logger.info("Submitted task %s ack=%s", ne_id, ack)
        except Exception as exc:
            logger.exception("Task %s failed", ne_id)
            submit_result(ne_id, worker_id, worker_token, -1, {"error": str(exc)})


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MethylPipeline reference REST worker")
    parser.add_argument("--worker-id", type=int, default=int(os.environ.get("WORKER_ID", "0")))
    parser.add_argument("--worker-token", default=os.environ.get("WORKER_TOKEN", ""))
    parser.add_argument("--capability", default=os.environ.get("WORKER_CAPABILITY"))
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("WORKER_POLL_SECONDS", "5")))
    parser.add_argument("--once", action="store_true", help="Poll once then exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.worker_id <= 0 or not args.worker_token:
        parser.error("Set --worker-id and --worker-token (or WORKER_ID / WORKER_TOKEN env vars)")

    if args.once:
        claim = request_task(args.worker_id, args.worker_token, args.capability)
        print(json.dumps(claim, indent=2))
        return 0

    poll_loop(args.worker_id, args.worker_token, args.capability, args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
