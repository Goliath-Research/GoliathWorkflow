#!/bin/bash
# Provision a GPU worker VM: Arc → MethylPipeline bundle → enroll → systemd daemon.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/provision_worker_node.sh [options]

Orchestrates worker onboarding on a VM with shared /work storage.
Requires sudo for Arc install and systemd.

Production workers are dumb HTTPS clients: portal preregisters the VM public IP,
then this script enrolls via the gateway (no Azure SQL credentials on the host).

Options:
  --root PATH              Epimethyl root (default: /work/epimethyl)
  --release-dir PATH       Release dir (default: <root>/current)
  --arch KEY               aarch64 or amd64
  --cluster KEY            wf.cluster cluster_key (default: epimethyl)
  --gpu                    Pass --gpu to bootstrap/setup_host
  --arc-onboard            Run install_arc_agent.sh (needs Azure env)
  --require-arc            Pass --require-arc to bootstrap / enroll
  --skip-promote           Use existing venv on /work (second+ VM)
  --enroll-worker          Enroll via methyl-worker enroll / register_worker enroll path
  --register-worker        Alias for --enroll-worker (legacy name; prefer enroll)
  --enable-systemd         Install and start methyl-worker units
  --capability NAME        Single capability (overrides auto-detect)
  --detect-capabilities    Install one systemd unit per detected capability
  --dry-run
  -h, --help

Env: WORKER_API_BASE (required for production enroll), AZ_SUBSCRIPTION_ID,
     AZ_RESOURCE_GROUP, AZURE_TENANT_ID.
     Direct DB vars (AZURE_SQL_*) are DEV-only for register_worker.py.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=detect_platform.sh
source "$SCRIPT_DIR/detect_platform.sh"

ROOT="${EPIMETHYL_ROOT:-/work/epimethyl}"
RELEASE_DIR=""
ARCH=""
CLUSTER="${CLUSTER_KEY:-epimethyl}"
GPU=0
ARC_ONBOARD=0
REQUIRE_ARC=0
SKIP_PROMOTE=0
REGISTER=0
ENABLE_SYSTEMD=0
CAPABILITY=""
DETECT_CAPABILITIES=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="${2:-}"; shift 2 ;;
    --release-dir) RELEASE_DIR="${2:-}"; shift 2 ;;
    --arch) ARCH="${2:-}"; shift 2 ;;
    --cluster) CLUSTER="${2:-}"; shift 2 ;;
    --gpu) GPU=1; shift ;;
    --arc-onboard) ARC_ONBOARD=1; shift ;;
    --require-arc) REQUIRE_ARC=1; shift ;;
    --skip-promote) SKIP_PROMOTE=1; shift ;;
    --enroll-worker|--register-worker) REGISTER=1; shift ;;
    --enable-systemd) ENABLE_SYSTEMD=1; shift ;;
    --capability) CAPABILITY="${2:-}"; shift 2 ;;
    --detect-capabilities) DETECT_CAPABILITIES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

ARCH="${ARCH:-$(platform_arch_key "$(detect_uname_arch)")}"
RELEASE_DIR="${RELEASE_DIR:-$ROOT/current}"
RUNTIME="$(readlink -f "$RELEASE_DIR/runtime-bundle" 2>/dev/null || echo "$REPO_ROOT")"
SCRIPTS="$RUNTIME/scripts"
[[ -d "$SCRIPTS" ]] || SCRIPTS="$SCRIPT_DIR"

echo "=== Preflight ==="
[[ -d "$ROOT" ]] || { echo "/work root missing: $ROOT" >&2; exit 1; }
if [[ "$GPU" -eq 1 ]]; then
  command -v nvidia-smi >/dev/null 2>&1 || echo "WARN: nvidia-smi not found"
fi

if [[ "$ARC_ONBOARD" -eq 1 ]]; then
  echo "=== Azure Arc ==="
  run sudo bash "$SCRIPTS/install_arc_agent.sh" \
    --subscription-id "${AZ_SUBSCRIPTION_ID:-}" \
    --resource-group "${AZ_RESOURCE_GROUP:-}" \
    --tenant-id "${AZURE_TENANT_ID:-}" \
    ${AZ_ARC_LOCATION:+--location "$AZ_ARC_LOCATION"}
fi

if [[ "$REQUIRE_ARC" -eq 1 ]]; then
  run bash "$SCRIPTS/verify_arc_prereqs.sh"
fi

echo "=== Host deps ==="
HOST_ARGS=(--system-deps --no-venv)
[[ "$GPU" -eq 1 ]] && HOST_ARGS+=(--gpu)
run bash "$SCRIPTS/setup_host.sh" "${HOST_ARGS[@]}"

echo "=== MethylPipeline bundle ==="
BOOT_ARGS=(--root "$ROOT" --arch "$ARCH")
[[ "$GPU" -eq 1 ]] && BOOT_ARGS+=(--gpu)
[[ "$REQUIRE_ARC" -eq 1 ]] && BOOT_ARGS+=(--require-arc)
if [[ "$SKIP_PROMOTE" -eq 1 ]]; then
  BOOT_ARGS+=(--release-dir "$RELEASE_DIR" --skip-parabricks-pull)
else
  BOOT_ARGS+=(--release-dir "$RELEASE_DIR" --promote-release)
fi
[[ -n "${WORKER_API_BASE:-}" ]] && export WORKER_API_BASE
run bash "$SCRIPTS/bootstrap_epimethyl.sh" "${BOOT_ARGS[@]}"

echo "=== Verify ==="
set -a
# shellcheck disable=SC1091
source "$ROOT/env/worker.env" 2>/dev/null || true
# shellcheck disable=SC1091
source "$ROOT/env/parabricks.env" 2>/dev/null || true
set +a
run bash "$SCRIPTS/verify_e2e_node.sh"

if [[ "$REGISTER" -eq 1 ]]; then
  echo "=== Enroll worker (gateway) ==="
  WORKER_KEY="$(hostname -s)"
  API_BASE="${WORKER_API_BASE:-${METHYL_API_BASE:-}}"
  VENV_PY=""
  for cand in "$ROOT/venv-$ARCH/bin/python" "$ROOT/venv/bin/python" "$REPO_ROOT/.venv/bin/python"; do
    if [[ -x "$cand" ]]; then
      VENV_PY="$cand"
      break
    fi
  done
  if [[ -n "$API_BASE" && -n "$VENV_PY" ]]; then
    ENROLL_ARGS=(enroll --api-base "$API_BASE" --cluster "$CLUSTER" --key "$WORKER_KEY")
    [[ -n "$CAPABILITY" ]] && ENROLL_ARGS+=(--capabilities-json "[\"$CAPABILITY\"]")
    [[ "$REQUIRE_ARC" -eq 1 ]] && run bash "$SCRIPTS/verify_arc_prereqs.sh"
    run "$VENV_PY" -m methyl_worker "${ENROLL_ARGS[@]}"
  else
    echo "WARN: WORKER_API_BASE unset or venv missing — falling back to register_worker.sh (dev/bootstrap)." >&2
    REG_ARGS=(--cluster "$CLUSTER" --key "$WORKER_KEY")
    if [[ -n "$CAPABILITY" ]]; then
      REG_ARGS+=(--capability "$CAPABILITY")
    fi
    [[ "$REQUIRE_ARC" -eq 1 ]] && REG_ARGS+=(--require-arc)
    run bash "$SCRIPTS/register_worker.sh" "${REG_ARGS[@]}"
  fi
fi

if [[ "$ENABLE_SYSTEMD" -eq 1 ]]; then
  echo "=== systemd ==="
  SD_ARGS=(--root "$ROOT" --arch "$ARCH" --runtime "$RUNTIME")
  if [[ -n "$CAPABILITY" ]]; then
    SD_ARGS+=(--capability "$CAPABILITY")
  elif [[ "$DETECT_CAPABILITIES" -eq 1 ]]; then
    SD_ARGS+=(--detect-capabilities)
  fi
  run sudo bash "$SCRIPTS/install_worker_systemd.sh" "${SD_ARGS[@]}"
fi

echo "Provision complete."
