#!/bin/bash
# Compile SamplePrep + StudyValidationLifecycle DomainPrograms and deploy via REST gateway.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_workflow_definitions.sh [options]

Options:
  --api-base URL       REST gateway base (default: WORKER_API_BASE or http://localhost:8080/v1)
  --output-dir PATH    Write compiled specs (default: /work/epimethyl/env/compiled)
  --versions-out PATH  workflow_version_id map (default: /work/epimethyl/env/workflow_versions.json)
  --dry-run            Compile only; do not POST
  -h, --help           Show this help
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

API_BASE="${WORKER_API_BASE:-http://localhost:8080/v1}"
OUTPUT_DIR="${EPIMETHYL_ENV_DIR:-/work/epimethyl/env}/compiled"
VERSIONS_OUT="${EPIMETHYL_ENV_DIR:-/work/epimethyl/env}/workflow_versions.json"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base) API_BASE="${2:-}"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:-}"; shift 2 ;;
    --versions-out) VERSIONS_OUT="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
fi

SAMPLE_PREP="$REPO_ROOT/workflow_engine/domain/fixtures/sample_prep.program.json"
REMEDIATE="$REPO_ROOT/workflow_engine/domain/fixtures/sample_prep_remediate.program.json"
LIFECYCLE="$REPO_ROOT/workflow_engine/domain/checks/pca1_5_cg/configs/study_validation_lifecycle.program.json"

for f in "$SAMPLE_PREP" "$REMEDIATE" "$LIFECYCLE"; do
  [[ -f "$f" ]] || { echo "Missing $f" >&2; exit 1; }
done

mkdir -p "$OUTPUT_DIR" "$(dirname "$VERSIONS_OUT")"

COMPILE="$REPO_ROOT/scripts/compile_workflow_program.py"
"$PYTHON_BIN" "$COMPILE" "$SAMPLE_PREP" -o "$OUTPUT_DIR/sample_prep_compiled.json"
"$PYTHON_BIN" "$COMPILE" "$REMEDIATE" -o "$OUTPUT_DIR/sample_prep_remediate_compiled.json"
"$PYTHON_BIN" "$COMPILE" "$LIFECYCLE" -o "$OUTPUT_DIR/study_validation_lifecycle_compiled.json"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry-run: compiled specs in $OUTPUT_DIR"
  exit 0
fi

"$PYTHON_BIN" - <<'PY' "$OUTPUT_DIR" "$API_BASE" "$VERSIONS_OUT"
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

out_dir = Path(sys.argv[1])
api_base = sys.argv[2].rstrip("/")
versions_out = Path(sys.argv[3])
results = {}

for path in sorted(out_dir.glob("*_compiled.json")):
    spec = json.loads(path.read_text(encoding="utf-8"))
    name = spec.get("name") or path.stem
    req = urllib.request.Request(
        f"{api_base}/workflows/definitions",
        data=json.dumps(spec).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"POST failed for {name}: HTTP {exc.code}: {detail}") from exc
    results[name] = body
    print(f"deployed {name}: workflow_version_id={body.get('workflow_version_id')}")

versions_out.parent.mkdir(parents=True, exist_ok=True)
versions_out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(f"wrote {versions_out}")
PY
