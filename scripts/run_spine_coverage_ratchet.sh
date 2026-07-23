#!/usr/bin/env bash
# Narrow, branch-aware coverage ratchet for the shared config-resolution spine.
#
# Unlike scripts/run_tests_ci.sh (global measure-and-report, no threshold), this
# enforces a real `fail_under` on the small set of modules that sit upstream of
# every typed action, where a regression is both high-blast-radius and invisible
# to the Pydantic boundary. Config lives in ci/coveragerc-spine.
#
# Usage (from repo root): ./scripts/run_spine_coverage_ratchet.sh [extra pytest args...]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "error: ${PY} not found. Create the project venv first (see docs/DEPLOYMENT.md)." >&2
  exit 1
fi

cd "$ROOT"

# Spine tests that exercise the gated modules directly.
SPINE_TESTS=(
  packages/methylutils/tests/test_action_config_resolver.py
  packages/methylutils/tests/test_cli_resolved_config.py
  packages/methylutils/tests/test_load_resolved_config.py
  packages/methylutils/tests/test_analyte_profiles.py
  packages/methylutils/tests/test_pangenome_config.py
  packages/methyldomain/tests/test_action_result.py
)

exec "$PY" -m pytest \
  "${SPINE_TESTS[@]}" \
  --cov-config=ci/coveragerc-spine \
  --cov=methyl_utils \
  --cov=methyl_domain \
  --cov-report=term-missing \
  "$@"
