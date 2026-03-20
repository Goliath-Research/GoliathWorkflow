#!/usr/bin/env bash
# Run the full pytest suite using the repository's canonical virtual environment.
# Usage (from repo root): ./scripts/run_tests.sh [pytest args...]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "error: ${PY} not found or not executable." >&2
  echo "Create and use the project venv from the repo root, then activate before developing:" >&2
  echo "  python3.12 -m venv .venv && source .venv/bin/activate && pip install -e packages/methylutils ..." >&2
  echo "See docs/DEPLOYMENT.md" >&2
  exit 1
fi
cd "$ROOT"
exec "$PY" -m pytest "$@"
