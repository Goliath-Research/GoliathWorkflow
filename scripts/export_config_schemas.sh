#!/usr/bin/env bash
# Regenerate committed JSON Schema artifacts under schemas/config/.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
methyl-export-config-schemas "$@"
