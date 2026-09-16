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
WORK_ROOT="${METHYL_WORK_ROOT:-${WORK_ROOT:-/work}}"
SITE="${METHYL_SITE_CONFIG:-$WORK_ROOT/site/methyl_site.json}"
check_path "Site manifest" "$SITE" 0

# Access modes: samples/projects/cache must be other-writable; genomes/site/goliath must not.
is_other_writable() {
  local perm last
  perm="$(stat -c '%a' "$1" 2>/dev/null || echo 0)"
  last="${perm: -1}"
  case "$last" in
    2|3|6|7) return 0 ;;
    *) return 1 ;;
  esac
}

check_other_writable() {
  local label="$1"
  local path="$2"
  local want_writable="$3"
  if [[ ! -d "$path" ]]; then
    warn "$label not found (optional): $path"
    return 0
  fi
  if is_other_writable "$path"; then
    if [[ "$want_writable" -eq 1 ]]; then
      ok "$label other-writable -> $path"
    else
      warn "$label is other-writable (expected worker-readable only): $path"
    fi
  else
    if [[ "$want_writable" -eq 1 ]]; then
      err "$label not other-writable (workers sharing this mount cannot write): $path — run scripts/init_work_layout.sh"
    else
      ok "$label worker-readable -> $path"
    fi
  fi
}

# samples is the hard contract (every worker + Docker must create/overwrite).
# projects/cache share the same init mode but do not fail an existing cluster.
# genomes/site/goliath should not be world-writable.
check_other_writable "Samples root" "$WORK_ROOT/samples" 1
if [[ -d "$WORK_ROOT/projects" ]] && ! is_other_writable "$WORK_ROOT/projects"; then
  warn "Projects root not other-writable: $WORK_ROOT/projects — run scripts/init_work_layout.sh"
elif [[ -d "$WORK_ROOT/projects" ]]; then
  ok "Projects root other-writable -> $WORK_ROOT/projects"
fi
if [[ -d "$WORK_ROOT/cache" ]] && ! is_other_writable "$WORK_ROOT/cache"; then
  warn "Cache root not other-writable: $WORK_ROOT/cache — run scripts/init_work_layout.sh"
elif [[ -d "$WORK_ROOT/cache" ]]; then
  ok "Cache root other-writable -> $WORK_ROOT/cache"
fi
check_other_writable "Genomes root" "$WORK_ROOT/genomes" 0
check_other_writable "Site root" "$WORK_ROOT/site" 0
check_other_writable "GoliathOmics root" "$WORK_ROOT/goliath" 0

# When site exists with reference_selection pins, require pinned genome files
if [[ -f "$SITE" ]]; then
  # shellcheck disable=SC1091
  if [[ -f "$ROOT/.venv/bin/activate" ]]; then
    # Prefer venv python for cfg.reference_selection
    # shellcheck disable=SC1091
    source "$ROOT/.venv/bin/activate" 2>/dev/null || true
  fi
  export WORK_ROOT
  export METHYL_SITE_CONFIG="$SITE"
  export PYTHONPATH="${ROOT}/workflow_engine${PYTHONPATH:+:$PYTHONPATH}"
  if python - <<'PY'
import json, os, sys
from pathlib import Path

site_path = Path(os.environ["METHYL_SITE_CONFIG"])
doc = json.loads(site_path.read_text(encoding="utf-8"))
sel = doc.get("reference_selection") or {}
if not any(sel.get(k) for k in ("linear", "gene_annotation", "pangenome")):
    print("SKIP: no genome reference_selection pins")
    sys.exit(0)
sys.path.insert(0, os.environ.get("PYTHONPATH", "").split(os.pathsep)[0])
from cfg.reference_selection import verify_selected_paths

res = verify_selected_paths(doc, work_root=os.environ.get("WORK_ROOT", "/work"))
if res["ok"]:
    print(f"OK: selected genome files ({len(res['present'])} paths)")
    sys.exit(0)
print("FAIL: missing pinned genome files:", file=sys.stderr)
for m in res["missing"]:
    print(f"  {m}", file=sys.stderr)
print(
    "Provision with scripts/provision_selected_genomes.sh "
    "(see docs/deployment/reference-inventory-qnap.md)",
    file=sys.stderr,
)
sys.exit(1)
PY
  then
    :
  else
    fail=1
  fi
fi

# Runtime bundle (production)
GOLIATH_CURRENT="${GOLIATH_CURRENT:-$WORK_ROOT/goliath/current}"
RUNTIME_BUNDLE="$GOLIATH_CURRENT/runtime-bundle"
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
if [[ -d /work/goliath/repos/MethylPipeline ]]; then
  warn "Git checkout present at /work/goliath/repos/MethylPipeline — production workers should use runtime-bundle only"
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
