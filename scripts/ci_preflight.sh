#!/usr/bin/env bash
# Local mirror of cheap PR / deployment sync guards (no full pytest suite).
#
# Run before push so sync-surface failures fail on the developer machine first.
# See docs/reference/ci-sync-matrix.md and docs/plans/ci-dev-deploy-sync.plan.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

PY="${PYTHON_BIN:-python3}"
if command -v python >/dev/null 2>&1; then
  PY=python
fi

echo "== doc freshness =="
bash scripts/check_doc_freshness.sh

echo "== doc links =="
bash scripts/check_doc_links.sh

echo "== no step_config in study manifests =="
"$PY" scripts/check_no_step_config.py

echo "== package install contract =="
"$PY" scripts/check_package_install_contract.py

echo "== catalog / golden / task schema files =="
"$PY" scripts/check_catalog_fixture_contract.py

echo "== diagram hash freshness =="
bash scripts/render_diagrams.sh --check

if command -v methyl-export-action-catalog >/dev/null 2>&1; then
  echo "== action catalog drift =="
  methyl-export-action-catalog --check
else
  echo "== action catalog drift == (skip: methyl-export-action-catalog not on PATH)"
fi

if command -v methyl-export-domain-schemas >/dev/null 2>&1; then
  echo "== domain schema drift =="
  methyl-export-domain-schemas --check
else
  echo "== domain schema drift == (skip: methyl-export-domain-schemas not on PATH)"
fi

echo "== SamplePrep DomainProgram graph / catalog =="
"$PY" - <<'PY'
import sys
from pathlib import Path
root = Path(".").resolve()
sys.path.insert(0, str(root / "workflow_engine" / "domain"))
from verify_workflow import verify_program_file
report = verify_program_file(root / "workflow_engine/domain/fixtures/sample_prep.program.json")
if not report.ok:
    print(report.to_dict())
    raise SystemExit(1)
print(f"SamplePrepPipeline ok nodes={report.node_count} actions={len(set(report.action_names))}")
PY

echo "CI preflight passed."
