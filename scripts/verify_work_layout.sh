#!/usr/bin/env bash
# Verify four-layer /work layout and runtime-bundle expectations (read-only).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0

warn() { echo "WARN: $*" >&2; }
err() { echo "FAIL: $*" >&2; fail=1; }
ok() { echo "OK: $*"; }

check_path() {
  local label="$1"
  local path="$2"
  local required="${3:-0}"
  if [[ -e "$path" ]]; then
    ok "$label -> $path"
  elif [[ "$required" -eq 1 ]]; then
    err "$label missing: $path"
  else
    warn "$label not found (optional): $path"
  fi
}

echo "==> Work layout verification"

# Site manifest
SITE="${METHYL_SITE_CONFIG:-/work/site/methyl_site.json}"
check_path "Site manifest" "$SITE" 0

# Runtime bundle (production)
EPIMETHYL_CURRENT="${EPIMETHYL_CURRENT:-/work/epimethyl/current}"
RUNTIME_BUNDLE="$EPIMETHYL_CURRENT/runtime-bundle"
check_path "Runtime bundle" "$RUNTIME_BUNDLE" 0
if [[ -d "$RUNTIME_BUNDLE/domain/profiles" ]]; then
  ok "Profile dir under runtime-bundle"
else
  warn "No profiles under $RUNTIME_BUNDLE/domain/profiles (dev may use repo paths)"
fi

# Repo profile dir (dev)
REPO_PROFILES="$ROOT/workflow_engine/domain/profiles"
check_path "Repo profiles" "$REPO_PROFILES" 1

# METHYL_PROFILE_DIR when set should exist
if [[ -n "${METHYL_PROFILE_DIR:-}" ]]; then
  check_path "METHYL_PROFILE_DIR" "$METHYL_PROFILE_DIR" 1
fi

# Example study manifest path (informational)
if [[ -n "${METHYL_VERIFY_PROJECT_PATH:-}" ]]; then
  check_path "METHYL_VERIFY_PROJECT_PATH" "$METHYL_VERIFY_PROJECT_PATH" 1
fi

# Git checkout on workers is discouraged in production
if [[ -d /work/epimethyl/repos/MethylPipeline ]]; then
  warn "Git checkout present at /work/epimethyl/repos/MethylPipeline — production workers should use runtime-bundle only"
fi

# Venv smoke
if [[ -x "$ROOT/.venv/bin/methyl-workflow-run" ]]; then
  ok "methyl-workflow-run in repo .venv"
else
  warn "methyl-workflow-run not in repo .venv (run make venv)"
fi

if [[ $fail -ne 0 ]]; then
  echo "Work layout verification failed." >&2
  exit 1
fi
echo "Work layout verification passed."
