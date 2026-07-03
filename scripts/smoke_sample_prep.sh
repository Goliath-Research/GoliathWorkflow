#!/bin/bash
# Smoke test: SamplePrepPipeline via methyl-study-start (admin CLI, not gateway domain routes).

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/smoke_sample_prep.sh [options]

Options:
  --api-base URL       Gateway base for instance polling (default: WORKER_API_BASE)
  --run-root PATH      Smoke fixture root (default: .smoke/sample_prep under repo)
  --poll-seconds N     Instance poll interval (default: 5)
  --timeout SEC        Max wait per instance (default: 600)
  --remediation        Reserved: run remediation-path smoke (second sample)
  -h, --help           Show this help

Requires:
  - Running REST gateway + PostgreSQL wf schema
  - Registered worker with WORKER_STUB_EXTERNAL=1
  - workflow_versions.json from deploy_workflow_definitions.sh
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

API_BASE="${WORKER_API_BASE:-http://localhost:8080/v1}"
RUN_ROOT="$REPO_ROOT/.smoke/sample_prep"
SAMPLE_ID="${SMOKE_SAMPLE_ID:-smoke-1}"
POLL=5
TIMEOUT=600
REMEDIATION=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base) API_BASE="${2:-}"; shift 2 ;;
    --run-root) RUN_ROOT="${2:-}"; shift 2 ;;
    --poll-seconds) POLL="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT="${2:-}"; shift 2 ;;
    --remediation) REMEDIATION=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
fi

VERSIONS_FILE="${EPIMETHYL_ENV_DIR:-/work/epimethyl/env}/workflow_versions.json"
if [[ ! -f "$VERSIONS_FILE" ]]; then
  VERSIONS_FILE="$REPO_ROOT/.smoke/workflow_versions.json"
fi

SMOKE_RUN_ROOT="$RUN_ROOT" bash "$SCRIPT_DIR/bootstrap_sample_prep_smoke_fixtures.sh" --run-root "$RUN_ROOT" --sample-id "$SAMPLE_ID"

"$PYTHON_BIN" - <<'PY' "$API_BASE" "$RUN_ROOT" "$VERSIONS_FILE" "$POLL" "$TIMEOUT" "$REMEDIATION" "$SAMPLE_ID" "$REPO_ROOT"
import json
import os
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

api_base = sys.argv[1].rstrip("/")
run_root = Path(sys.argv[2])
versions_file = Path(sys.argv[3])
poll = int(sys.argv[4])
timeout = int(sys.argv[5])
remediation = int(sys.argv[6])
sample_id = sys.argv[7]
repo_root = Path(sys.argv[8])
wf_engine = repo_root / "workflow_engine"

project_path = run_root / "project.json"

def request(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if body else {},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))

def poll_instance(instance_id: int) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        inst = request("GET", f"/workflows/instances/{instance_id}")
        status = inst.get("status") or inst.get("workflow_status")
        print(f"instance {instance_id} status={status}", flush=True)
        if status in ("COMPLETED", "FAILED", "CANCELLED"):
            return str(status)
        time.sleep(poll)
    raise TimeoutError(f"instance {instance_id} not terminal after {timeout}s")

versions = {}
if versions_file.is_file():
    versions = json.loads(versions_file.read_text(encoding="utf-8"))

sample_prep_vid = (
    versions.get("SamplePrepPipeline", {}).get("workflow_version_id")
    or versions.get("sample_prep_compiled", {}).get("workflow_version_id")
)
if not sample_prep_vid:
    raise SystemExit(
        f"workflow_version_id missing in {versions_file}; run deploy_workflow_definitions.sh"
    )

body = {
    "projectPath": str(project_path.resolve()),
    "workflow_version_id": int(sample_prep_vid),
    "samples": [
        {
            "sampleId": sample_id,
            "sampleDir": str((run_root / "samples" / sample_id).resolve()),
            "fastqPrefix": f"{sample_id}/",
        }
    ],
    "fastqStorage": {
        "type": "file",
        "basePath": str(run_root / "fastq"),
    },
    "sampleStorage": {
        "type": "file",
        "basePath": str(run_root / "archive"),
    },
}
if remediation:
    print("note: --remediation not yet implemented; running default pass-path smoke")

body_json = json.dumps(body)
wf_engine = repo_root / "workflow_engine"
env = os.environ.copy()
env["PYTHONPATH"] = str(wf_engine)
proc = subprocess.run(
    [sys.executable, "-m", "admin.study_start", "sample-prep-start", "-"],
    input=body_json,
    capture_output=True,
    text=True,
    cwd=str(wf_engine),
    env=env,
)
if proc.returncode != 0:
    raise SystemExit(f"methyl-study-start failed: {proc.stderr or proc.stdout}")
started = json.loads(proc.stdout)
instance_id = int(started["instance_id"])
print(json.dumps({"planned_samples": started.get("n_samples"), "context_samples": len(started.get("context_json", {}).get("samples", []))}, indent=2))

status = poll_instance(instance_id)
if status != "COMPLETED":
    raise SystemExit(f"SamplePrep smoke failed: {status}")

archive_root = run_root / "archive"
archive_prefix = archive_root / sample_id
h5_path = archive_prefix / "h5" / "21-CG.h5"
manifest_path = archive_prefix / "archive_manifest.json"
if not h5_path.is_file():
    raise SystemExit(f"archive smoke check failed: missing {h5_path}")
if not manifest_path.is_file():
    raise SystemExit(f"archive smoke check failed: missing {manifest_path}")

print("smoke_sample_prep: OK")
print(json.dumps({"instance_id": instance_id, "status": status}, indent=2))
PY
