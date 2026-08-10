#!/bin/bash
# Provision a GPU worker VM for join-only cluster attach.
# Default: skip promote; install local Docker/CTK; optional staged Arc + enroll.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/provision_worker_node.sh [options]

Orchestrates worker onboarding on a VM with shared /work storage.
Requires sudo for Docker/Arc install and systemd.

Production workers are dumb HTTPS clients: portal preregisters the VM public IP,
then this script enrolls via the gateway (no Azure SQL credentials on the host).

Join modes:
  --join-mode join      Default. Use existing /work/epimethyl/current; skip promote
                        and skip Parabricks pull (Lambda happy path).
  --join-mode first     Escape hatch: promote release from this VM (needs release
                        dir + NGC on an admin/promote host — not typical Lambda).

Staged Arc (recommended when you approve Connected Machines):
  --prepare-only        Host tools + Docker/CTK + verify; stop before Arc/enroll
  --finish-enroll       Assume prepare done + Arc Connected; enroll + systemd

Options:
  --root PATH              Epimethyl root (default: /work/epimethyl)
  --release-dir PATH       Release dir (default: <root>/current)
  --arch KEY               aarch64 or amd64
  --cluster KEY            wf.cluster cluster_key (default: epimethyl)
  --gpu                    Pass --gpu to bootstrap/setup_host; require nvidia-smi
  --join-mode MODE         join (default) | first
  --skip-promote           Alias for --join-mode join (legacy)
  --prepare-only           Stop after local install + verify
  --finish-enroll          Enroll + systemd only (implies --require-arc unless skipped)
  --arc-onboard            Run install_arc_agent.sh (needs Azure env)
  --require-arc            Pass --require-arc to bootstrap / enroll
  --enroll-worker          Enroll via methyl-worker enroll / register_worker enroll path
  --register-worker        Alias for --enroll-worker (legacy name; prefer enroll)
  --enable-systemd         Install and start methyl-worker units
  --capability NAME        Single capability (overrides auto-detect)
  --detect-capabilities    Install one systemd unit per detected capability
  --skip-preflight         Skip preflight_worker_join.sh
  --dry-run
  -h, --help

Env: WORKER_API_BASE (required for production enroll), AZ_SUBSCRIPTION_ID,
     AZ_RESOURCE_GROUP, AZURE_TENANT_ID.
     Direct DB vars (AZURE_SQL_*) are DEV-only for register_worker.py.

See docs/deployment/lambda_worker_join.md
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
JOIN_MODE="join"
ARC_ONBOARD=0
REQUIRE_ARC=0
REGISTER=0
ENABLE_SYSTEMD=0
PREPARE_ONLY=0
FINISH_ENROLL=0
CAPABILITY=""
DETECT_CAPABILITIES=0
SKIP_PREFLIGHT=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="${2:-}"; shift 2 ;;
    --release-dir) RELEASE_DIR="${2:-}"; shift 2 ;;
    --arch) ARCH="${2:-}"; shift 2 ;;
    --cluster) CLUSTER="${2:-}"; shift 2 ;;
    --gpu) GPU=1; shift ;;
    --join-mode)
      JOIN_MODE="${2:-}"
      shift 2
      ;;
    --skip-promote) JOIN_MODE="join"; shift ;;
    --prepare-only) PREPARE_ONLY=1; shift ;;
    --finish-enroll) FINISH_ENROLL=1; shift ;;
    --arc-onboard) ARC_ONBOARD=1; shift ;;
    --require-arc) REQUIRE_ARC=1; shift ;;
    --enroll-worker|--register-worker) REGISTER=1; shift ;;
    --enable-systemd) ENABLE_SYSTEMD=1; shift ;;
    --capability) CAPABILITY="${2:-}"; shift 2 ;;
    --detect-capabilities) DETECT_CAPABILITIES=1; shift ;;
    --skip-preflight) SKIP_PREFLIGHT=1; shift ;;
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

case "$JOIN_MODE" in
  join|first) ;;
  *) echo "Invalid --join-mode: $JOIN_MODE (use join|first)" >&2; exit 1 ;;
esac

if [[ "$PREPARE_ONLY" -eq 1 && "$FINISH_ENROLL" -eq 1 ]]; then
  echo "Use either --prepare-only or --finish-enroll, not both" >&2
  exit 1
fi

# finish-enroll always needs Arc verify + enroll/systemd defaults
if [[ "$FINISH_ENROLL" -eq 1 ]]; then
  REQUIRE_ARC=1
  REGISTER=1
  ENABLE_SYSTEMD=1
fi

ARCH="${ARCH:-$(platform_arch_key "$(detect_uname_arch)")}"
RELEASE_DIR="${RELEASE_DIR:-$ROOT/current}"
RUNTIME="$(readlink -f "$RELEASE_DIR/runtime-bundle" 2>/dev/null || echo "$REPO_ROOT")"
SCRIPTS="$RUNTIME/scripts"
[[ -d "$SCRIPTS" ]] || SCRIPTS="$SCRIPT_DIR"

do_enroll() {
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
    if [[ -n "$CAPABILITY" ]]; then
      ENROLL_ARGS+=(--capabilities-json "[\"$CAPABILITY\"]")
    fi
    [[ "$REQUIRE_ARC" -eq 1 ]] && run bash "$SCRIPTS/verify_arc_prereqs.sh"
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/env/worker.env" 2>/dev/null || true
    # shellcheck disable=SC1091
    source "$ROOT/env/parabricks.env" 2>/dev/null || true
    set +a
    run env PYTHONPATH="${REPO_ROOT}/workers${PYTHONPATH:+:$PYTHONPATH}" \
      "$VENV_PY" -m methyl_worker "${ENROLL_ARGS[@]}"
  else
    echo "WARN: WORKER_API_BASE unset or venv missing — falling back to register_worker.sh (dev/bootstrap)." >&2
    REG_ARGS=(--cluster "$CLUSTER" --key "$WORKER_KEY")
    if [[ -n "$CAPABILITY" ]]; then
      REG_ARGS+=(--capability "$CAPABILITY")
    fi
    [[ "$REQUIRE_ARC" -eq 1 ]] && REG_ARGS+=(--require-arc)
    run bash "$SCRIPTS/register_worker.sh" "${REG_ARGS[@]}"
  fi
}

do_systemd() {
  echo "=== systemd ==="
  SD_ARGS=(--root "$ROOT" --arch "$ARCH" --runtime "$RUNTIME")
  if [[ -n "$CAPABILITY" ]]; then
    SD_ARGS+=(--capability "$CAPABILITY")
  elif [[ "$DETECT_CAPABILITIES" -eq 1 ]]; then
    SD_ARGS+=(--detect-capabilities)
  fi
  run sudo bash "$SCRIPTS/install_worker_systemd.sh" "${SD_ARGS[@]}"
}

# --- finish-enroll: short approved window after Arc ---
if [[ "$FINISH_ENROLL" -eq 1 ]]; then
  if [[ "$SKIP_PREFLIGHT" -eq 0 ]]; then
    PF_ARGS=(--root "$ROOT" --require-current --require-api)
    [[ "$GPU" -eq 1 ]] && PF_ARGS+=(--gpu)
    run bash "$SCRIPTS/preflight_worker_join.sh" "${PF_ARGS[@]}"
  fi
  run bash "$SCRIPTS/verify_arc_prereqs.sh"
  do_enroll
  do_systemd
  echo "Finish-enroll complete."
  exit 0
fi

# --- prepare / full path ---
if [[ "$SKIP_PREFLIGHT" -eq 0 ]]; then
  echo "=== Preflight ==="
  PF_ARGS=(--root "$ROOT")
  if [[ "$JOIN_MODE" == "join" ]]; then
    PF_ARGS+=(--require-current)
  else
    PF_ARGS+=(--allow-missing-current)
  fi
  [[ "$GPU" -eq 1 ]] && PF_ARGS+=(--gpu)
  if [[ "$REGISTER" -eq 1 && "$PREPARE_ONLY" -eq 0 ]]; then
    PF_ARGS+=(--require-api)
  fi
  run bash "$SCRIPTS/preflight_worker_join.sh" "${PF_ARGS[@]}"
fi

if [[ "$PREPARE_ONLY" -eq 0 && "$ARC_ONBOARD" -eq 1 ]]; then
  echo "=== Azure Arc ==="
  run sudo bash "$SCRIPTS/install_arc_agent.sh" \
    --subscription-id "${AZ_SUBSCRIPTION_ID:-}" \
    --resource-group "${AZ_RESOURCE_GROUP:-}" \
    --tenant-id "${AZURE_TENANT_ID:-}" \
    ${AZ_ARC_LOCATION:+--location "$AZ_ARC_LOCATION"}
fi

if [[ "$PREPARE_ONLY" -eq 0 && "$REQUIRE_ARC" -eq 1 ]]; then
  run bash "$SCRIPTS/verify_arc_prereqs.sh"
fi

echo "=== Host deps ==="
HOST_ARGS=(--system-deps --no-venv)
[[ "$GPU" -eq 1 ]] && HOST_ARGS+=(--gpu)
run bash "$SCRIPTS/setup_host.sh" "${HOST_ARGS[@]}"

echo "=== MethylPipeline bundle (join-mode=$JOIN_MODE) ==="
BOOT_ARGS=(--root "$ROOT" --arch "$ARCH" --release-dir "$RELEASE_DIR")
[[ "$GPU" -eq 1 ]] && BOOT_ARGS+=(--gpu)
# Prepare must not fail closed on Arc; full path may require it
if [[ "$PREPARE_ONLY" -eq 0 && "$REQUIRE_ARC" -eq 1 ]]; then
  BOOT_ARGS+=(--require-arc)
fi
if [[ "$JOIN_MODE" == "first" ]]; then
  BOOT_ARGS+=(--promote-release)
else
  # Join: install Docker/CTK locally; never re-pull Parabricks layers
  BOOT_ARGS+=(--skip-parabricks-pull)
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

if [[ "$PREPARE_ONLY" -eq 1 ]]; then
  echo "Prepare-only complete (Docker/host tools installed; Arc/enroll not run)."
  echo "Next:"
  echo "  1. Approve Azure Arc Connected for this machine"
  echo "  2. bash $SCRIPTS/verify_arc_prereqs.sh"
  echo "  3. sudo bash $SCRIPTS/provision_worker_node.sh --gpu --join-mode join --finish-enroll --cluster $CLUSTER"
  exit 0
fi

if [[ "$REGISTER" -eq 1 ]]; then
  do_enroll
fi

if [[ "$ENABLE_SYSTEMD" -eq 1 ]]; then
  do_systemd
fi

echo "Provision complete."
