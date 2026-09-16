#!/usr/bin/env bash
# Run the full pytest regression suite with machine-readable outputs for CI.
#
# Emits:
#   test-results/junit.xml       -> GitHub Actions artifact (JUnit)
#   coverage/coverage.xml        -> GitHub Actions artifact (Cobertura)
#   coverage/html/               -> browsable HTML coverage report
#
# Policy: coverage is MEASURED and REPORTED only. There is deliberately no
# --cov-fail-under gate yet (see docs/regulatory/
# continuous-integration-and-regression-testing.md). GPU tests are deselected
# because hosted CI agents have no GPU; DB/`/work`-fixture tests self-skip.
#
# Usage (from repo root): ./scripts/run_tests_ci.sh [extra pytest args...]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "error: ${PY} not found or not executable." >&2
  echo "Create the project venv from the repo root first. See docs/DEPLOYMENT.md" >&2
  exit 1
fi

cd "$ROOT"
mkdir -p test-results coverage

exec "$PY" -m pytest \
  -m "not gpu" \
  --junitxml=test-results/junit.xml \
  --cov \
  --cov-report=xml:coverage/coverage.xml \
  --cov-report=html:coverage/html \
  --cov-report=term-missing \
  "$@"
