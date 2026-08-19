#!/bin/bash
# Provision a GPU worker VM: first seeds shared /work, joiners enroll then install VM-local.
# Database bootstrap is a privileged-host step — this script never runs DDL or SQL register.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/provision_worker_node.sh [options]

Join modes:
  --join-mode auto      Default. Missing /work/epimethyl/current/manifest.json → first;
                        present → join.
  --join-mode join      Enroll first, then VM-local only (never promote / Parabricks pull).
  --join-mode first     Seed shared /work (layout, release, extractor, one Parabricks pull),
                        then enroll, then systemd.

Staged Arc:
  --prepare-only        Host tools + Docker/CTK + shared seed (first) or skip enroll
  --finish-enroll       Enroll + systemd (requires live WORKER_API_BASE)

Options:
  --root PATH              Epimethyl root on /work (default: /work/epimethyl)
  --release-dir PATH       Release dir for first-worker promote (default: <root>/current)
  --arch KEY               aarch64 or amd64
  --cluster KEY            wf.cluster cluster_key (default: epimethyl)
  --gpu                    Pass --gpu to bootstrap/setup_host; require nvidia-smi
  --join-mode MODE         auto (default) | join | first
  --skip-promote           Alias for --join-mode join
  --prepare-only
  --finish-enroll
  --arc-onboard            Run install_arc_agent.sh
  --require-arc            Verify Arc Connected before enroll
  --enroll-worker          Enroll via methyl-worker enroll (implied by --finish-enroll)
  --register-worker        Rejected: production enroll is gateway-only
  --enable-systemd         Install methyl-worker units
  --capability NAME
  --detect-capabilities
  --skip-preflight
  --dry-run
  -h, --help

Env: WORKER_API_BASE (required for enroll). Portal must already preregister this VM's public IP.
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
JOIN_MODE="auto"
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
    --enroll-worker) REGISTER=1; shift ;;
    --register-worker)
      echo "Direct-DB register is not allowed on GPU workers." >&2
      echo "Portal-preregister this VM, then methyl-worker enroll (WORKER_API_BASE)." >&2
      exit 2
      ;;
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

die() { echo "[ERROR] $*" >&2; exit 1; }

case "$JOIN_MODE" in
  auto|join|first) ;;
  *) die "Invalid --join-mode: $JOIN_MODE (use auto|join|first)" ;;
esac

if [[ "$PREPARE_ONLY" -eq 1 && "$FINISH_ENROLL" -eq 1 ]]; then
  die "Use either --prepare-only or --finish-enroll, not both"
fi

if [[ "$FINISH_ENROLL" -eq 1 ]]; then
  REQUIRE_ARC=1
  REGISTER=1
  ENABLE_SYSTEMD=1
fi

ARCH="${ARCH:-$(platform_arch_key "$(detect_uname_arch)")}"
RELEASE_DIR="${RELEASE_DIR:-$ROOT/current}"
MANIFEST="$ROOT/current/manifest.json"

if [[ "$JOIN_MODE" == "auto" ]]; then
  if [[ -f "$MANIFEST" ]]; then
    JOIN_MODE="join"
  else
    JOIN_MODE="first"
  fi
  echo "Auto-detected join-mode=$JOIN_MODE (manifest $([[ -f "$MANIFEST" ]] && echo present || echo missing))"
fi

RUNTIME="$(readlink -f "$RELEASE_DIR/runtime-bundle" 2>/dev/null || true)"
[[ -d "${RUNTIME:-}" ]] || RUNTIME="$(readlink -f "$ROOT/current/runtime-bundle" 2>/dev/null || true)"
[[ -d "${RUNTIME:-}" ]] || RUNTIME="$REPO_ROOT"
SCRIPTS="$RUNTIME/scripts"
[[ -d "$SCRIPTS" ]] || SCRIPTS="$SCRIPT_DIR"

resolve_venv_python() {
  local cand
  for cand in "$ROOT/venv-$ARCH/bin/python" "$ROOT/venv/bin/python"; do
    if [[ -x "$cand" ]]; then
      echo "$cand"
      return 0
    fi
  done
  return 1
}

do_enroll() {
  echo "=== Enroll worker (gateway) ==="
  local api_base="${WORKER_API_BASE:-${METHYL_API_BASE:-}}"
  [[ -n "$api_base" ]] || die "WORKER_API_BASE (or METHYL_API_BASE) is required — no SQL register on GPU VMs"
  local venv_py=""
  venv_py="$(resolve_venv_python)" || die "Worker venv python not found under $ROOT/venv-$ARCH (seed /work first)"
  local worker_key
  worker_key="$(hostname -s)"
  [[ "$REQUIRE_ARC" -eq 1 ]] && run bash "$SCRIPTS/verify_arc_prereqs.sh"
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/env/worker.env" 2>/dev/null || true
  # shellcheck disable=SC1091
  source "$ROOT/env/parabricks.env" 2>/dev/null || true
  set +a
  api_base="${WORKER_API_BASE:-${METHYL_API_BASE:-$api_base}}"
  local enroll_args=(enroll --api-base "$api_base" --cluster "$CLUSTER" --key "$worker_key")
  if [[ -n "$CAPABILITY" ]]; then
    enroll_args+=(--capabilities-json "[\"$CAPABILITY\"]")
  fi
  run env PYTHONPATH="${REPO_ROOT}/workers${PYTHONPATH:+:$PYTHONPATH}" \
    "$venv_py" -m methyl_worker "${enroll_args[@]}"
}

do_systemd() {
  echo "=== systemd ==="
  local sd_args=(--root "$ROOT" --arch "$ARCH" --runtime "$RUNTIME")
  if [[ -n "$CAPABILITY" ]]; then
    sd_args+=(--capability "$CAPABILITY")
  elif [[ "$DETECT_CAPABILITIES" -eq 1 ]]; then
    sd_args+=(--detect-capabilities)
  fi
  run sudo bash "$SCRIPTS/install_worker_systemd.sh" "${sd_args[@]}"
}

do_host_and_docker() {
  local skip_pb="$1"
  echo "=== Host deps ==="
  local host_args=(--system-deps --no-venv)
  [[ "$GPU" -eq 1 ]] && host_args+=(--gpu)
  run bash "$SCRIPTS/setup_host.sh" "${host_args[@]}"

  echo "=== MethylPipeline bundle (join-mode=$JOIN_MODE) ==="
  local boot_args=(--root "$ROOT" --arch "$ARCH" --release-dir "$RELEASE_DIR")
  [[ "$GPU" -eq 1 ]] && boot_args+=(--gpu)
  if [[ "$PREPARE_ONLY" -eq 0 && "$REQUIRE_ARC" -eq 1 ]]; then
    boot_args+=(--require-arc)
  fi
  if [[ "$skip_pb" -eq 1 ]]; then
    boot_args+=(--skip-parabricks-pull)
  else
    boot_args+=(--promote-release)
  fi
  [[ -n "${WORKER_API_BASE:-}" ]] && export WORKER_API_BASE
  run bash "$SCRIPTS/bootstrap_epimethyl.sh" "${boot_args[@]}"
}

do_shared_seed() {
  echo "=== Seed shared /work (first worker) ==="
  local work_root
  work_root="$(dirname "$ROOT")"
  if [[ -x "$SCRIPTS/init_work_layout.sh" ]]; then
    run bash "$SCRIPTS/init_work_layout.sh" --work "$work_root"
  fi
  [[ -d "$RELEASE_DIR" ]] || die "Release directory not found: $RELEASE_DIR (assemble/promote artifacts onto /work first)"
  do_host_and_docker 0
  local work_root_check="$work_root"
  if [[ ! -d "$work_root_check/genomes" || ! -d "$work_root_check/site" ]]; then
    echo "NOTE: $work_root_check/genomes or $work_root_check/site missing after layout seed."
    echo "      Download references onto the share (methyl-cfg provision-assets / scripts/provision_selected_genomes.sh)."
  fi
}

if [[ "$FINISH_ENROLL" -eq 1 ]]; then
  if [[ "$SKIP_PREFLIGHT" -eq 0 ]]; then
    local_pf=(--root "$ROOT" --require-current --require-api)
    [[ "$GPU" -eq 1 ]] && local_pf+=(--gpu)
    run bash "$SCRIPTS/preflight_worker_join.sh" "${local_pf[@]}"
  fi
  run bash "$SCRIPTS/verify_arc_prereqs.sh"
  do_enroll
  do_systemd
  echo "Finish-enroll complete."
  exit 0
fi

if [[ "$SKIP_PREFLIGHT" -eq 0 ]]; then
  echo "=== Preflight ==="
  pf_args=(--root "$ROOT")
  if [[ "$JOIN_MODE" == "join" ]]; then
    pf_args+=(--require-current)
  else
    pf_args+=(--allow-missing-current)
  fi
  [[ "$GPU" -eq 1 ]] && pf_args+=(--gpu)
  if [[ "$REGISTER" -eq 1 || "$JOIN_MODE" == "join" ]] && [[ "$PREPARE_ONLY" -eq 0 ]]; then
    pf_args+=(--require-api)
  fi
  run bash "$SCRIPTS/preflight_worker_join.sh" "${pf_args[@]}"
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

if [[ "$JOIN_MODE" == "join" ]]; then
  if [[ "$PREPARE_ONLY" -eq 0 ]]; then
    REGISTER=1
    do_enroll
  fi
  do_host_and_docker 1
else
  do_shared_seed
  if [[ "$PREPARE_ONLY" -eq 0 ]]; then
    REGISTER=1
    do_enroll
  fi
fi

echo "=== Verify ==="
set -a
# shellcheck disable=SC1091
source "$ROOT/env/worker.env" 2>/dev/null || true
# shellcheck disable=SC1091
source "$ROOT/env/parabricks.env" 2>/dev/null || true
set +a
run bash "$SCRIPTS/verify_e2e_node.sh"

if [[ "$PREPARE_ONLY" -eq 1 ]]; then
  echo "Prepare-only complete."
  if [[ "$JOIN_MODE" == "first" ]]; then
    echo "Shared /work seeded. Start the gateway if needed, then --finish-enroll."
  else
    echo "Next: enroll with WORKER_API_BASE set: $0 --join-mode join --finish-enroll --cluster $CLUSTER"
  fi
  exit 0
fi

if [[ "$ENABLE_SYSTEMD" -eq 1 ]]; then
  do_systemd
fi

echo "Provision complete (join-mode=$JOIN_MODE)."
