#!/bin/bash
# Bootstrap MethylPipeline + MethylExtractor on shared storage (/work/epimethyl).
# Host-native worker provisioning: .venv, Python packages, MethylExtractor build, env files.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_epimethyl.sh [options]

Options:
  --root PATH              Shared storage root (default: /work/epimethyl)
  --pipeline-url URL       MethylPipeline git remote
  --extractor-url URL      MethylExtractor git remote
  --branch NAME            Git branch for both repos (default: current or main)
  --system-deps            Pass --system-deps to setup_host.sh
  --gpu                    Force GPU Python requirements
  --skip-docker            Skip setup_gpu_node.sh
  --skip-parabricks-pull   Do not docker pull Parabricks image
  --skip-methyl-extractor  Skip MethylExtractor build
  --dry-run                Print actions without executing
  -h, --help               Show this help

Environment:
  EPIMETHYL_ROOT             Same as --root
  METHYL_PIPELINE_URL        Git URL for MethylPipeline
  METHYL_EXTRACTOR_URL       Git URL for MethylExtractor
  WORKER_API_BASE            Written to worker.env (default: http://localhost:8080/v1)
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=detect_platform.sh
source "$SCRIPT_DIR/detect_platform.sh"

ROOT="${EPIMETHYL_ROOT:-/work/epimethyl}"
PIPELINE_URL="${METHYL_PIPELINE_URL:-}"
EXTRACTOR_URL="${METHYL_EXTRACTOR_URL:-}"
BRANCH=""
SYSTEM_DEPS=0
GPU_FLAG=0
SKIP_DOCKER=0
SKIP_PARABRICKS_PULL=0
SKIP_METHYL_EXTRACTOR=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="${2:-}"; shift 2 ;;
    --pipeline-url) PIPELINE_URL="${2:-}"; shift 2 ;;
    --extractor-url) EXTRACTOR_URL="${2:-}"; shift 2 ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --system-deps) SYSTEM_DEPS=1; shift ;;
    --gpu) GPU_FLAG=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --skip-parabricks-pull) SKIP_PARABRICKS_PULL=1; shift ;;
    --skip-methyl-extractor) SKIP_METHYL_EXTRACTOR=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

info() { echo "[INFO] $*"; }
warn() { echo "[WARN] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

UNAME_ARCH="$(detect_uname_arch)"
ARCH_KEY="$(platform_arch_key "$UNAME_ARCH")"
ME_SUBDIR="$(resolve_methyl_extractor_subdir "$UNAME_ARCH")"
PARABRICKS_IMAGE="${METHYL_PARABRICKS_IMAGE:-$(resolve_parabricks_image)}"

REPOS="$ROOT/repos"
PIPELINE_DIR="$REPOS/MethylPipeline"
EXTRACTOR_DIR="$REPOS/MethylExtractor"
VENV_DIR="$ROOT/venv"
ENV_DIR="$ROOT/env"
DATA_DIR="$ROOT/data"
RUNS_DIR="$ROOT/runs"

info "Bootstrap epimethyl"
info "  root: $ROOT"
info "  arch: $UNAME_ARCH ($ARCH_KEY)"
info "  parabricks: ${PARABRICKS_IMAGE:-<unset>}"

clone_or_update() {
  local url="$1"
  local dest="$2"
  local name
  name="$(basename "$dest")"

  if [[ -z "$url" ]]; then
    if [[ -d "$dest/.git" ]]; then
      info "Using existing checkout: $dest"
      if [[ -n "$BRANCH" ]]; then
        run git -C "$dest" fetch origin
        run git -C "$dest" checkout "$BRANCH"
        run git -C "$dest" pull --ff-only origin "$BRANCH" || true
      fi
      return 0
    fi
    if [[ "$name" == "MethylPipeline" && -d "$REPO_ROOT/.git" ]]; then
      info "Seeding MethylPipeline from current checkout: $REPO_ROOT -> $dest"
      run mkdir -p "$(dirname "$dest")"
      if [[ ! -d "$dest" ]]; then
        run cp -a "$REPO_ROOT" "$dest"
      fi
      return 0
    fi
    die "No git URL for $name and $dest does not exist. Set METHYL_PIPELINE_URL / METHYL_EXTRACTOR_URL or clone manually."
  fi

  run mkdir -p "$(dirname "$dest")"
  if [[ -d "$dest/.git" ]]; then
    info "Updating $dest"
    run git -C "$dest" fetch origin
    if [[ -n "$BRANCH" ]]; then
      run git -C "$dest" checkout "$BRANCH"
      run git -C "$dest" pull --ff-only origin "$BRANCH" || true
    else
      run git -C "$dest" pull --ff-only || true
    fi
  else
    info "Cloning $url -> $dest"
    local clone_args=("$url" "$dest")
    if [[ -n "$BRANCH" ]]; then
      clone_args=(--branch "$BRANCH" "${clone_args[@]}")
    fi
    run git clone "${clone_args[@]}"
  fi
}

run mkdir -p "$REPOS" "$ENV_DIR" "$DATA_DIR" "$RUNS_DIR"

clone_or_update "$PIPELINE_URL" "$PIPELINE_DIR"
clone_or_update "$EXTRACTOR_URL" "$EXTRACTOR_DIR"

SETUP_ARGS=(--venv "$VENV_DIR")
if [[ "$SYSTEM_DEPS" -eq 1 ]]; then
  SETUP_ARGS+=(--system-deps)
fi
if [[ "$GPU_FLAG" -eq 1 ]]; then
  SETUP_ARGS+=(--gpu)
fi

info "Running setup_host.sh ..."
run bash "$PIPELINE_DIR/scripts/setup_host.sh" "${SETUP_ARGS[@]}"

info "Running install_all.sh ..."
if [[ "$DRY_RUN" -eq 0 ]]; then
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
fi
INSTALL_ARGS=(--pipeline-reqs)
if [[ "$GPU_FLAG" -eq 1 ]] || command -v nvidia-smi >/dev/null 2>&1; then
  INSTALL_ARGS+=(--gpu-reqs)
fi
run bash "$PIPELINE_DIR/scripts/install_all.sh" "${INSTALL_ARGS[@]}" --skip-marp

if [[ "$SKIP_METHYL_EXTRACTOR" -eq 0 && -d "$EXTRACTOR_DIR" ]]; then
  info "Building MethylExtractor ($ME_SUBDIR) ..."
  run bash -c "cd '$EXTRACTOR_DIR' && make"
  if [[ "$DRY_RUN" -eq 0 ]]; then
  ME_BIN="$EXTRACTOR_DIR/build/dynamic/$ME_SUBDIR/MethylExtractor"
    if [[ ! -x "$ME_BIN" ]]; then
      die "MethylExtractor binary not found at $ME_BIN"
    fi
    PLUGIN_DIR="$EXTRACTOR_DIR/build/dynamic/$ME_SUBDIR/hdf5_zstd_plugin"
  else
    ME_BIN="$EXTRACTOR_DIR/build/dynamic/$ME_SUBDIR/MethylExtractor"
    PLUGIN_DIR="$EXTRACTOR_DIR/build/dynamic/$ME_SUBDIR/hdf5_zstd_plugin"
  fi
else
  ME_BIN="${METHYL_EXTRACTOR_BIN:-MethylExtractor}"
  PLUGIN_DIR="/usr/local/hdf5/lib/plugin"
fi

if [[ "$SKIP_DOCKER" -eq 0 ]]; then
  GPU_ARGS=(--env-dir "$ENV_DIR")
  if [[ "$SKIP_PARABRICKS_PULL" -eq 0 ]]; then
    GPU_ARGS+=(--pull-parabricks)
  fi
  if [[ -x "$PIPELINE_DIR/scripts/setup_gpu_node.sh" ]]; then
    run bash "$PIPELINE_DIR/scripts/setup_gpu_node.sh" "${GPU_ARGS[@]}"
  fi
fi

WORKER_API_BASE="${WORKER_API_BASE:-http://localhost:8080/v1}"

if [[ "$DRY_RUN" -eq 0 ]]; then
  cat >"$ENV_DIR/worker.env" <<EOF
# Generated by scripts/bootstrap_epimethyl.sh
EPIMETHYL_ROOT=$ROOT
WORKER_API_BASE=$WORKER_API_BASE
# WORKER_ID=
# WORKER_TOKEN=
# WORKER_CAPABILITY=
METHYL_EXTRACTOR_BIN=$ME_BIN
HDF5_PLUGIN_PATH=$PLUGIN_DIR
PATH=$VENV_DIR/bin:\$PATH
EOF
  if [[ -n "$PARABRICKS_IMAGE" ]]; then
    echo "METHYL_PARABRICKS_IMAGE=$PARABRICKS_IMAGE" >>"$ENV_DIR/worker.env"
    echo "METHYL_PARABRICKS_GPU_FLAGS=--gpus all" >>"$ENV_DIR/worker.env"
  fi
  if [[ -f "$ENV_DIR/parabricks.env" ]]; then
    echo "# Also see parabricks.env" >>"$ENV_DIR/worker.env"
  fi
  info "Wrote $ENV_DIR/worker.env"
else
  info "[DRY-RUN] Would write $ENV_DIR/worker.env"
fi

info "Bootstrap complete."
info "Next steps:"
info "  1. source $ENV_DIR/worker.env"
info "  2. Register worker: $PIPELINE_DIR/scripts/register_worker.sh"
info "  3. Verify node: $PIPELINE_DIR/scripts/verify_e2e_node.sh"
