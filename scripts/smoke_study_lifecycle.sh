#!/bin/bash
# Smoke test: stubbed SamplePrep + StudyValidationLifecycle via REST gateway.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/smoke_study_lifecycle.sh [options]

Options:
  --api-base URL       Gateway base (default: WORKER_API_BASE)
  --project PATH       Project JSON (default: smoke project in pca1_5_cg bundle)
  --poll-seconds N     Instance poll interval (default: 5)
  --timeout SEC        Max wait per instance (default: 600)
  -h, --help           Show this help

Requires:
  - Running REST gateway + PostgreSQL wf schema
  - Registered worker with WORKER_STUB_EXTERNAL=1 (omnibus or sample-prep capable)
  - workflow_versions.json from deploy_workflow_definitions.sh (or env overrides)
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

API_BASE="${WORKER_API_BASE:-http://localhost:8080/v1}"
PROJECT_PATH="$REPO_ROOT/workflow_engine/domain/checks/pca1_5_cg/configs/project_Healthy_vs_PCa1-5-CG_smoke.json"
VERSIONS_FILE="${EPIMETHYL_ENV_DIR:-/work/epimethyl/env}/workflow_versions.json"
POLL=5
TIMEOUT=600

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base) API_BASE="${2:-}"; shift 2 ;;
    --project) PROJECT_PATH="${2:-}"; shift 2 ;;
    --poll-seconds) POLL="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
fi

[[ -f "$PROJECT_PATH" ]] || { echo "Project not found: $PROJECT_PATH" >&2; exit 1; }

"$PYTHON_BIN" - <<'PY' "$API_BASE" "$PROJECT_PATH" "$VERSIONS_FILE" "$POLL" "$TIMEOUT"
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

api_base = sys.argv[1].rstrip("/")
project_path = sys.argv[2]
versions_file = Path(sys.argv[3])
poll = int(sys.argv[4])
timeout = int(sys.argv[5])

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
lifecycle_vid = (
    versions.get("StudyValidationLifecycle", {}).get("workflow_version_id")
    or versions.get("study_validation_lifecycle_compiled", {}).get("workflow_version_id")
)

if not sample_prep_vid or not lifecycle_vid:
    raise SystemExit(
        f"workflow_version_id missing in {versions_file}; run deploy_workflow_definitions.sh"
    )

# Instance 1: SamplePrep with stub-friendly single sample
prep_ctx = {
    "projectPath": project_path,
    "primaryAnalyte": "buffy_coat",
    "isCfdna": False,
    "referenceFasta": "/work/epimethyl/data/reference.fa",
    "fastqStorage": {
        "type": "file",
        "basePath": "/work/epimethyl/runs/smoke/fastq",
    },
    "samples": [
        {
            "sampleId": "smoke-1",
            "sampleDir": "/work/epimethyl/runs/smoke/samples/smoke-1",
            "fastqPrefix": "smoke-1/",
        }
    ],
}
prep = request(
    "POST",
    "/workflows/instances",
    {"workflow_version_id": int(sample_prep_vid), "context_json": prep_ctx},
)
prep_id = int(prep["workflow_instance_id"] if "workflow_instance_id" in prep else prep["instance_id"])
request("POST", f"/workflows/instances/{prep_id}/start", {})
prep_status = poll_instance(prep_id)
if prep_status != "COMPLETED":
    raise SystemExit(f"SamplePrep smoke failed: {prep_status}")

# Instance 2: StudyValidationLifecycle via gateway helper
val = request(
    "POST",
    "/studies/validation/start",
    {
        "projectPath": project_path,
        "workflow_version_id": int(lifecycle_vid),
        "featureIterations": 2,
        "seed": 42,
    },
)
val_id = int(val["instance_id"])
val_status = poll_instance(val_id)
if val_status != "COMPLETED":
    raise SystemExit(f"StudyValidationLifecycle smoke failed: {val_status}")

print("smoke_study_lifecycle: OK")
print(json.dumps({"sample_prep_instance_id": prep_id, "validation_instance_id": val_id}, indent=2))
PY
