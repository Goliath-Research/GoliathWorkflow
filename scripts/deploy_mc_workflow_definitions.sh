#!/usr/bin/env bash
# Compile and deploy MC / lifecycle DomainPrograms with parallel centroid seed phase.
#
# Usage:
#   source .venv/bin/activate
#   export BACKEND_DB=mssql   # or postgres
#   # set AZURE_SQL_* or POSTGRES_* (see deploy/env/gateway.*.env.example)
#   bash scripts/deploy_mc_workflow_definitions.sh
#
# Options:
#   --dry-run          Compile only
#   --delete-instances Pass delete_instances=true on replace deploy (default: false)
#   -h, --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DRY_RUN=0
DELETE_INSTANCES=0

usage() {
  sed -n '2,16p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base|--use-gateway)
      echo "Note: gateway deploy removed; using direct DB only ($1 ignored)" >&2
      if [[ "$1" == "--api-base" ]]; then shift 2; else shift; fi
      ;;
    --dry-run) DRY_RUN=1; shift ;;
    --delete-instances) DELETE_INSTANCES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN=python3

COMPILE="$REPO_ROOT/scripts/compile_workflow_program.py"
OUT_ROOT="${EPIMETHYL_ENV_DIR:-/work/epimethyl/env}/compiled/mc"

PROGRAMS=(
  "workflow_engine/domain/checks/pca1_5_cg/configs/pca1_5_mc_stability.program.json"
  "workflow_engine/domain/checks/pca1_5_cg/configs/pca1_5_mc_stability_smoke.program.json"
  "workflow_engine/domain/checks/pca1_5_cg/configs/study_validation_lifecycle.program.json"
  "workflow_engine/domain/checks/pca1_5_cg/configs/pca1_5_full_lifecycle.program.json"
  "workflow_engine/domain/checks/pca1_5_cg/configs/mc_gene_enricher_stability.program.json"
  "workflow_engine/domain/checks/pca1_5_cg/configs/healthy_pca_mc_stability.program.json"
  "workflow_engine/domain/checks/buffy_healthy_vs_pca/configs/buffy_mc_stability.program.json"
  "workflow_engine/domain/checks/h_pca_good/configs/h_pca_good_mc_stability.program.json"
)

mkdir -p "$OUT_ROOT"
COMPILED=()
for rel in "${PROGRAMS[@]}"; do
  src="$REPO_ROOT/$rel"
  [[ -f "$src" ]] || { echo "Missing $src" >&2; exit 1; }
  stem="$(basename "$rel" .program.json)"
  out="$OUT_ROOT/${stem}_compiled.json"
  "$PYTHON_BIN" "$COMPILE" "$src" -o "$out"
  COMPILED+=("$out")
  echo "compiled: $out"
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry-run: specs in $OUT_ROOT"
  exit 0
fi

"$PYTHON_BIN" - "$REPO_ROOT" "$DELETE_INSTANCES" "${COMPILED[@]}" <<'PY'
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
delete_instances = sys.argv[2] == "1"
compiled_paths = [Path(p) for p in sys.argv[3:]]

sys.path.insert(0, str(repo / "workflow_engine"))
from ops.workflow_deploy import deploy_workflow_definition
from rest.connection import resolve_connection_config
from rest.db import open_gateway_db

config = resolve_connection_config()
db = open_gateway_db(config)
try:
    for path in compiled_paths:
        spec = json.loads(path.read_text(encoding="utf-8"))
        result = deploy_workflow_definition(
            db,
            {"spec": spec, "replace": True, "delete_instances": delete_instances},
            create_workflow_definition=db.create_workflow_definition,
            delete_workflow_definition=db.delete_workflow_definition,
        )
        db.commit()
        print(f"deployed {spec.get('name')}: workflow_version_id={result.get('workflow_version_id')}")
finally:
    db.close()
PY
