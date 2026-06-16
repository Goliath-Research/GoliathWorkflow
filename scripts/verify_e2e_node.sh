#!/bin/bash
# End-to-end node verification for GPU worker hosts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ENV_FILE="${EPIMETHYL_ENV_FILE:-/work/epimethyl/env/worker.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.venv/bin/activate"
elif [[ -f "${EPIMETHYL_ROOT:-/work/epimethyl}/venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${EPIMETHYL_ROOT:-/work/epimethyl}/venv/bin/activate"
fi

echo "============================================="
echo "E2E node verification"
echo "============================================="
echo ""

FAIL=0

run_check() {
  local name="$1"
  shift
  if "$@"; then
    echo "OK  $name"
  else
    echo "FAIL $name"
    FAIL=1
  fi
}

run_check "verify_setup" bash "$REPO_ROOT/scripts/verify_setup.sh"

if command -v nvidia-smi >/dev/null 2>&1 && [[ -n "${METHYL_PARABRICKS_IMAGE:-}" ]]; then
  run_check "verify_parabricks" bash "$REPO_ROOT/scripts/verify_parabricks.sh"
else
  echo "SKIP verify_parabricks (no GPU image or nvidia-smi)"
fi

if [[ -n "${METHYL_EXTRACTOR_BIN:-}" ]] || command -v MethylExtractor >/dev/null 2>&1; then
  run_check "verify_methyl_extractor" bash "$REPO_ROOT/scripts/verify_methyl_extractor.sh"
else
  echo "SKIP verify_methyl_extractor (MethylExtractor not configured)"
fi

run_check "methyl-worker --help" methyl-worker --help

if [[ -n "${WORKER_ID:-}" && -n "${WORKER_TOKEN:-}" && -n "${WORKER_API_BASE:-}" ]]; then
  echo "Worker credentials present in environment (WORKER_ID=$WORKER_ID)"
else
  echo "WARN worker credentials not set; run scripts/register_worker.sh"
fi

echo ""
if [[ "$FAIL" -eq 0 ]]; then
  echo "E2E node verification passed"
  exit 0
fi
echo "E2E node verification failed"
exit 1
