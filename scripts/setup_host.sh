#!/bin/bash
# Host (non-Docker) environment setup script
# Installs pipeline-level dependencies and local packages

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/setup_host.sh [options]

Options:
  --system-deps     Install system packages (Ubuntu/Debian via apt)
  --gpu             Install GPU requirements (CUDA 12.x stack)
  --venv PATH       Create/use a virtualenv at PATH (default: .venv)
  --no-venv         Do not create or activate a virtualenv
  --with-deps       Allow pip to resolve package deps (override --no-deps)
  -h, --help        Show this help

Notes:
  - This script is intended for host installs (not inside Docker).
  - Most Python dependencies are installed from requirements-pipeline.txt.
  - Use --gpu to install GPU packages from requirements-gpu.txt.
EOF
}

info() { echo "[INFO] $*"; }
warn() { echo "[WARN] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

SYSTEM_DEPS=0
GPU_DEPS=0
NO_VENV=0
VENV_DIR=""
WITH_DEPS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --system-deps) SYSTEM_DEPS=1; shift ;;
    --gpu) GPU_DEPS=1; shift ;;
    --venv) VENV_DIR="${2:-}"; shift 2 ;;
    --no-venv) NO_VENV=1; shift ;;
    --with-deps) WITH_DEPS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

if [ -f "/.dockerenv" ] || [ -f "/run/.containerenv" ]; then
  die "Detected container environment. Use Docker setup scripts instead."
fi

install_system_deps() {
  if ! command -v apt-get >/dev/null 2>&1; then
    die "apt-get not found. Install system dependencies manually."
  fi

  local sudo_cmd=""
  if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
      sudo_cmd="sudo"
    else
      die "sudo not available; re-run as root or install dependencies manually."
    fi
  fi

  info "Installing system dependencies (Ubuntu/Debian)..."
  $sudo_cmd apt-get update
  $sudo_cmd apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3.10-venv \
    python3-pip \
    build-essential \
    git \
    hdf5-tools \
    libhdf5-dev \
    libzstd-dev \
    curl \
    gnupg \
    apt-transport-https \
    unixodbc-dev

  if ! dpkg -s msodbcsql18 >/dev/null 2>&1; then
    info "Installing Microsoft ODBC Driver 18..."
    $sudo_cmd curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | \
      $sudo_cmd gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" | \
      $sudo_cmd tee /etc/apt/sources.list.d/mssql-release.list >/dev/null
    $sudo_cmd apt-get update
    $sudo_cmd ACCEPT_EULA=Y apt-get install -y msodbcsql18
  else
    info "msodbcsql18 already installed."
  fi
}

if [ "$SYSTEM_DEPS" -eq 1 ]; then
  install_system_deps
fi

choose_python() {
  local candidates=("python3.10" "python3" "python")
  for cand in "${candidates[@]}"; do
    if command -v "$cand" >/dev/null 2>&1; then
      "$cand" - <<'PY' >/dev/null 2>&1 || continue
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
      echo "$cand"
      return 0
    fi
  done
  return 1
}

PYTHON_BIN="$(choose_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  die "Python 3.10+ is required but was not found."
fi

if [ "$NO_VENV" -eq 0 ]; then
  if [ -n "${VIRTUAL_ENV:-}" ]; then
    info "Using active virtualenv: $VIRTUAL_ENV"
    PYTHON_BIN="python"
  else
    VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
    if [ ! -d "$VENV_DIR" ]; then
      info "Creating virtualenv at $VENV_DIR"
      "$PYTHON_BIN" -m venv "$VENV_DIR"
    else
      info "Using existing virtualenv at $VENV_DIR"
    fi
    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"
    PYTHON_BIN="python"
  fi
else
  info "Skipping virtualenv setup."
fi

REQ_BASE="$PROJECT_ROOT/requirements-pipeline.txt"
REQ_GPU="$PROJECT_ROOT/requirements-gpu.txt"

if [ ! -f "$REQ_BASE" ]; then
  die "Missing $REQ_BASE"
fi

info "Upgrading pip tooling..."
"$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel

info "Installing pipeline-level Python requirements..."
"$PYTHON_BIN" -m pip install -r "$REQ_BASE"

if [ "$GPU_DEPS" -eq 1 ]; then
  if [ ! -f "$REQ_GPU" ]; then
    die "Missing $REQ_GPU"
  fi
  info "Installing GPU requirements (CUDA 12.x)..."
  "$PYTHON_BIN" -m pip install -r "$REQ_GPU" --extra-index-url https://pypi.nvidia.com
fi

PIP_DEPS_FLAG=("--no-deps")
if [ "$WITH_DEPS" -eq 1 ]; then
  PIP_DEPS_FLAG=()
fi

PACKAGES=(
  "methylutils"
  "methylcentroid"
  "methyldetector"
  "methylmapper"
  "methylclassifier"
  "methylenricher"
  "methylcluster"
  "methylalignmentqc"
)

info "Installing local packages (editable mode)..."
for pkg in "${PACKAGES[@]}"; do
  PKG_PATH="$PROJECT_ROOT/packages/$pkg"
  if [ -d "$PKG_PATH" ]; then
    info "Installing $pkg"
    "$PYTHON_BIN" -m pip install -e "$PKG_PATH" "${PIP_DEPS_FLAG[@]}"
  else
    warn "Skipping $pkg (directory not found)"
  fi
done

info "Host setup complete."
info "Test imports:"
info "  $PYTHON_BIN -c \"from methyl_utils import get_logger; print('OK')\""
