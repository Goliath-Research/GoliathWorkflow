#!/usr/bin/env bash
# Regenerate committed JSON Schema artifacts under schemas/config/.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
# Match pytest pythonpath (pyproject.toml) so ProjectConfig and step models resolve from source trees.
export PYTHONPATH="${ROOT}/packages/methylutils:${ROOT}/packages/methylcentroid:${ROOT}/packages/methyldetector:${ROOT}/packages/methylclassifier:${ROOT}/packages/methylpredictor:${ROOT}/packages/methylvalidation:${ROOT}/packages/methylmapper:${ROOT}/packages/methylcluster:${ROOT}/packages/methylenricher:${ROOT}/packages/methylalignmentqc:${ROOT}/packages/methyldiseaseprogression"
methyl-export-config-schemas "$@"
