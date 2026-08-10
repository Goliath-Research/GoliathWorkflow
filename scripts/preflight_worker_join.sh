#!/bin/bash
# Fail-closed preflight for joining a GPU worker to an existing QNAP-backed cluster.
# Does not mount NFS and does not promote releases.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/preflight_worker_join.sh [options]

Checks that shared /work is usable for a join-only worker provision.

Options:
  --root PATH           Epimethyl root (default: /work/epimethyl)
  --work PATH           Parent /work mount (default: dirname of --root, usually /work)
  --require-current     Require <root>/current/manifest.json (default: on)
  --allow-missing-current  Do not require current/manifest.json
  --gpu                 Require nvidia-smi
  --require-api         Require WORKER_API_BASE (or METHYL_API_BASE) in the environment
  --writable-probe      Write/remove a probe file under <root> (default: on)
  --skip-writable-probe Skip writable probe
  -h, --help

Exit 0 on success. Prints a clear next step when the release is missing.
EOF
}

ROOT="${EPIMETHYL_ROOT:-/work/epimethyl}"
WORK=""
REQUIRE_CURRENT=1
GPU=0
REQUIRE_API=0
WRITABLE_PROBE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="${2:-}"; shift 2 ;;
    --work) WORK="${2:-}"; shift 2 ;;
    --require-current) REQUIRE_CURRENT=1; shift ;;
    --allow-missing-current) REQUIRE_CURRENT=0; shift ;;
    --gpu) GPU=1; shift ;;
    --require-api) REQUIRE_API=1; shift ;;
    --writable-probe) WRITABLE_PROBE=1; shift ;;
    --skip-writable-probe) WRITABLE_PROBE=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

info() { echo "[OK] $*"; }
warn() { echo "[WARN] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

WORK="${WORK:-$(dirname "$ROOT")}"
MANIFEST="$ROOT/current/manifest.json"

echo "=== Worker join preflight ==="
echo "  work: $WORK"
echo "  root: $ROOT"

[[ -d "$WORK" ]] || die "Shared work mount missing: $WORK (ops must mount QNAP → /work before join)"
[[ -d "$ROOT" ]] || die "Epimethyl root missing: $ROOT (expected under the QNAP share)"

if [[ "$WRITABLE_PROBE" -eq 1 ]]; then
  PROBE="$ROOT/.join_preflight_$$"
  if ! (umask 077; echo ok >"$PROBE") 2>/dev/null; then
    die "Cannot write under $ROOT — check mount permissions / NFS export"
  fi
  rm -f "$PROBE"
  info "Writable probe under $ROOT"
fi

if [[ "$REQUIRE_CURRENT" -eq 1 ]]; then
  if [[ ! -f "$MANIFEST" ]]; then
    cat >&2 <<EOF
[ERROR] Release not promoted on the share: missing $MANIFEST

Next step (cluster bootstrap — not on this worker):
  1. Run Epimethyl-Release-Assemble + approved Epimethyl-Release-Deploy
  2. Confirm /work/epimethyl/current/manifest.json exists on QNAP
  3. Pull Parabricks once into /work/epimethyl/docker on a promote host (NGC)
  4. Re-run this preflight, then provision_worker_node.sh --join-mode join

See docs/deployment/lambda_worker_join.md
EOF
    exit 1
  fi
  info "Found $MANIFEST"
else
  warn "Skipping current/manifest.json check (--allow-missing-current)"
fi

if [[ "$GPU" -eq 1 ]]; then
  command -v nvidia-smi >/dev/null 2>&1 || die "nvidia-smi not found (install NVIDIA drivers before --gpu join)"
  info "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo unknown)"
fi

if [[ "$REQUIRE_API" -eq 1 ]]; then
  API_BASE="${WORKER_API_BASE:-${METHYL_API_BASE:-}}"
  [[ -n "$API_BASE" ]] || die "WORKER_API_BASE (or METHYL_API_BASE) is unset — export the gateway /v1 URL before enroll"
  info "WORKER_API_BASE=$API_BASE"
fi

info "Preflight passed"
exit 0
