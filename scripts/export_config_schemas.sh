#!/usr/bin/env bash
# Regenerate committed JSON Schema artifacts under schemas/config/.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
# Match pytest pythonpath (pyproject.toml) so ProjectConfig and step models resolve from source trees.
export PYTHONPATH="${ROOT}/packages/methylutils:${ROOT}/packages/methylcentroid:${ROOT}/packages/methyldetector:${ROOT}/packages/methylclassifier:${ROOT}/packages/methylpredictor:${ROOT}/packages/methylvalidation:${ROOT}/packages/methylmapper:${ROOT}/packages/methylcluster:${ROOT}/packages/methylenricher:${ROOT}/packages/methylalignmentqc:${ROOT}/packages/methylextractionqc:${ROOT}/packages/methylfragmentomics:${ROOT}/packages/methylderivedmeasures:${ROOT}/packages/methyldeconv:${ROOT}/packages/methylinfotheory:${ROOT}/packages/methyldiseaseprogression:${ROOT}/packages/methyldomain:${ROOT}/packages/rnaalignmentqc:${ROOT}/packages/rnaexpress:${ROOT}/packages/omicsfeatures:${ROOT}/packages/proteomicsfeatures:${ROOT}/packages/proteomicsqc"
methyl-export-config-schemas "$@"
