#!/bin/bash
# Compile SamplePrep + StudyValidationLifecycle DomainPrograms and deploy via direct DB.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_workflow_definitions.sh [options]

Options:
  --output-dir PATH    Write compiled specs (default: /work/epimethyl/env/compiled)
  --versions-out PATH  workflow_version_id map (default: /work/epimethyl/env/workflow_versions.json)
  --dry-run            Compile only; do not deploy
  -h, --help           Show this help

Requires BACKEND_DB + AZURE_SQL_* or POSTGRES_* (see deploy/env/gateway.*.env.example).
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

OUTPUT_DIR="${EPIMETHYL_ENV_DIR:-/work/epimethyl/env}/compiled"
VERSIONS_OUT="${EPIMETHYL_ENV_DIR:-/work/epimethyl/env}/workflow_versions.json"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base) echo "Note: --api-base ignored (direct DB deploy only)" >&2; shift 2 ;;
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

"$PYTHON_BIN" - "$REPO_ROOT" "$OUTPUT_DIR" "$VERSIONS_OUT" <<'PY'
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
versions_out = Path(sys.argv[3])
sys.path.insert(0, str(repo / "workflow_engine"))

from ops.workflow_deploy import deploy_workflow_definition
from rest.connection import resolve_connection_config
from rest.db import open_gateway_db

config = resolve_connection_config()
db = open_gateway_db(config)
results = {}
try:
    for path in sorted(out_dir.glob("*_compiled.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        name = spec.get("name") or path.stem
        result = deploy_workflow_definition(
            db,
            {"spec": spec, "replace": True, "delete_instances": True},
            create_workflow_definition=db.create_workflow_definition,
            delete_workflow_definition=db.delete_workflow_definition,
        )
        db.commit()
        results[name] = result
        print(f"deployed {name}: workflow_version_id={result.get('workflow_version_id')}")
finally:
    db.close()

versions_out.parent.mkdir(parents=True, exist_ok=True)
versions_out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(f"wrote {versions_out}")
PY
