#!/bin/bash
# Host (non-Docker) environment setup script
# Installs pipeline-level dependencies and local packages

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/setup_host.sh [options]

Options:
  --system-deps     Install system packages (Ubuntu/Debian via apt)
  --gpu             Install GPU requirements (CUDA 12.x or 13.x, auto-detected)
  --no-gpu          Skip GPU requirements (override auto-detect)
  --venv PATH       Create/use a virtualenv at PATH (default: .venv)
  --no-venv         Do not create or activate a virtualenv
  --with-deps       Allow pip to resolve package deps (override --no-deps)
  -h, --help        Show this help

Notes:
  - This script is intended for host installs (not inside Docker).
  - Most Python dependencies are installed from requirements-pipeline.txt.
  - Use --gpu to install GPU packages from requirements-gpu*.txt (CuPy, cuDF, torch).
  - If Python headers/build tools are missing, hdbscan is installed only
    when a prebuilt wheel is available; otherwise it is skipped with a warning.

Libraries in use (for verification):
  - Base: requirements-pipeline.txt (scipy, h5py, hdf5plugin, pandas, numpy, etc.).
  - GPU: requirements-gpu-cuda12.txt or requirements-gpu.txt (cupy, cudf, torch).
  - System (--system-deps): Python dev, build-essential, hdf5-tools, libhdf5-dev,
    libzstd-dev, ODBC; with GPU, libnvrtc{N} for NVRTC.
EOF
}

info() { echo "[INFO] $*"; }
warn() { echo "[WARN] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

SYSTEM_DEPS=0
GPU_DEPS=0
NO_GPU=0
NO_VENV=0
VENV_DIR=""
WITH_DEPS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --system-deps) SYSTEM_DEPS=1; shift ;;
    --gpu) GPU_DEPS=1; shift ;;
    --no-gpu) NO_GPU=1; shift ;;
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

detect_gpu() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    return 0
  fi
  if [ -e /proc/driver/nvidia/version ] || [ -e /dev/nvidiactl ] || [ -e /dev/nvidia0 ]; then
    return 0
  fi
  return 1
}

# Detect CUDA major version (12 or 13) from nvidia-smi or nvcc. Echoes version and returns 0, or echoes 12 and returns 1 if unclear.
detect_cuda_version() {
  local ver=""
  if command -v nvidia-smi >/dev/null 2>&1; then
    ver="$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: *\([0-9][0-9]*\.[0-9]*\).*/\1/p' | head -1)"
  fi
  if [ -z "$ver" ] && command -v nvcc >/dev/null 2>&1; then
    ver="$(nvcc --version 2>/dev/null | sed -n 's/.*release \([0-9][0-9]*\.[0-9]*\).*/\1/p' | head -1)"
  fi
  if [ -z "$ver" ] && [ -f /usr/local/cuda/version.txt ]; then
    ver="$(sed -n 's/^CUDA Version \([0-9][0-9]*\.[0-9]*\).*/\1/p' /usr/local/cuda/version.txt | head -1)"
  fi
  if [ -n "$ver" ]; then
    local major="${ver%%.*}"
    if [ "$major" = "13" ] || [ "$major" = "12" ]; then
      echo "$major"
      return 0
    fi
  fi
  echo "12"
  return 1
}

# Check for libnvrtc.so.$cuda_major (e.g. .12 or .13). $1 = CUDA major.
libnvrtc_present() {
  local cuda_major="${1:-12}"
  local patterns=()

  if [ -n "${VIRTUAL_ENV:-}" ]; then
    patterns+=("${VIRTUAL_ENV}/lib/python*/site-packages/nvidia/cuda_nvrtc/lib/libnvrtc.so.${cuda_major}")
    patterns+=("${VIRTUAL_ENV}/lib/python*/site-packages/nvidia/cu${cuda_major}/lib/libnvrtc.so.${cuda_major}")
  fi
  patterns+=(
    "${PROJECT_ROOT}/.venv/lib/python*/site-packages/nvidia/cuda_nvrtc/lib/libnvrtc.so.${cuda_major}"
    "${PROJECT_ROOT}/.venv/lib/python*/site-packages/nvidia/cu${cuda_major}/lib/libnvrtc.so.${cuda_major}"
    "/usr/lib/aarch64-linux-gnu/libnvrtc.so.${cuda_major}"
    "/usr/lib/x86_64-linux-gnu/libnvrtc.so.${cuda_major}"
    "/usr/local/cuda/lib64/libnvrtc.so.${cuda_major}"
    "/usr/local/cuda/targets/*/lib/libnvrtc.so.${cuda_major}"
    "/usr/local/cuda-*/targets/*/lib/libnvrtc.so.${cuda_major}"
  )

  for pattern in "${patterns[@]}"; do
    if [ -n "$pattern" ] && compgen -G "$pattern" > /dev/null; then
      return 0
    fi
  done
  return 1
}

# Install system NVRTC packages for CUDA major version. $1 = CUDA major (12 or 13).
install_nvrtc_system_deps() {
  local cuda_major="${1:-12}"
  if libnvrtc_present "$cuda_major"; then
    return 0
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    warn "apt-get not found; cannot install libnvrtc system packages."
    return 1
  fi

  local sudo_cmd=""
  if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
      sudo_cmd="sudo"
    else
      warn "sudo not available; cannot install libnvrtc system packages."
      return 1
    fi
  fi

  info "Installing NVRTC runtime libraries (libnvrtc.so.${cuda_major})..."
  $sudo_cmd apt-get update
  if ! $sudo_cmd apt-get install -y "libnvrtc${cuda_major}" "libnvrtc-builtins${cuda_major}"; then
    warn "Failed to install libnvrtc${cuda_major} packages. Ensure NVIDIA CUDA repo is configured."
    return 1
  fi

  if libnvrtc_present "$cuda_major"; then
    info "NVRTC runtime libraries detected."
    return 0
  fi

  warn "libnvrtc.so.${cuda_major} still not found after installation attempt."
  return 1
}

install_system_deps() {
  if ! command -v apt-get >/dev/null 2>&1; then
    die "apt-get not found. Install system dependencies manually."
  fi

  local python_packages=()
  if apt-cache show python3.10-dev >/dev/null 2>&1; then
    python_packages=(python3.10 python3.10-dev python3.10-venv)
  else
    python_packages=(python3 python3-dev python3-venv)
    warn "python3.10 packages not available; using default python3."
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
    "${python_packages[@]}" \
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

# Auto-enable GPU requirements when a GPU is detected (unless explicitly disabled)
CUDA_MAJOR=""
if [ "$GPU_DEPS" -eq 0 ] && [ "$NO_GPU" -eq 0 ]; then
  if detect_gpu; then
    info "NVIDIA GPU detected; enabling GPU Python requirements."
    GPU_DEPS=1
    CUDA_MAJOR="$(detect_cuda_version)" || true
    if [ -z "$CUDA_MAJOR" ]; then CUDA_MAJOR="12"; fi
    info "Detected CUDA ${CUDA_MAJOR}.x."
  fi
fi
# When --gpu is passed explicitly, detect CUDA version for NVRTC/requirements
if [ "$GPU_DEPS" -eq 1 ] && [ -z "$CUDA_MAJOR" ]; then
  CUDA_MAJOR="$(detect_cuda_version)" || true
  if [ -z "$CUDA_MAJOR" ]; then CUDA_MAJOR="12"; fi
  info "Using CUDA ${CUDA_MAJOR}.x for GPU requirements."
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

python_headers_present() {
  "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1 || return 1
import os
import sys
import sysconfig

include_dir = sysconfig.get_config_var("INCLUDEPY") or sysconfig.get_path("include") or ""
sys.exit(0 if include_dir and os.path.isfile(os.path.join(include_dir, "Python.h")) else 1)
PY
}

filter_requirements_without_hdbscan() {
  local src="$1"
  local dest="$2"
  "$PYTHON_BIN" - <<'PY' "$src" "$dest"
import pathlib
import sys

src, dest = sys.argv[1:]
lines = []
for line in pathlib.Path(src).read_text().splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        lines.append(line)
        continue
    if stripped.split(";", 1)[0].strip().lower().startswith("hdbscan"):
        continue
    lines.append(line)
pathlib.Path(dest).write_text("\n".join(lines) + "\n")
PY
}

REQ_BASE="$PROJECT_ROOT/requirements-pipeline.txt"
# GPU requirements file depends on detected CUDA major (12 vs 13)
if [ "$GPU_DEPS" -eq 1 ]; then
  if [ "${CUDA_MAJOR:-12}" = "12" ]; then
    REQ_GPU="$PROJECT_ROOT/requirements-gpu-cuda12.txt"
  else
    REQ_GPU="$PROJECT_ROOT/requirements-gpu.txt"
  fi
else
  REQ_GPU="$PROJECT_ROOT/requirements-gpu.txt"
fi

if [ ! -f "$REQ_BASE" ]; then
  die "Missing $REQ_BASE"
fi

info "Upgrading pip tooling..."
"$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel

info "Installing pipeline-level Python requirements..."
REQ_INSTALL="$REQ_BASE"
REQ_TMP=""
HDBSCAN_CAN_BUILD=1

if ! python_headers_present; then
  warn "Python headers not found; hdbscan source build disabled."
  HDBSCAN_CAN_BUILD=0
fi
if ! command -v gcc >/dev/null 2>&1; then
  warn "gcc not found; hdbscan source build disabled."
  HDBSCAN_CAN_BUILD=0
fi
if ! command -v make >/dev/null 2>&1; then
  warn "make not found; hdbscan source build disabled."
  HDBSCAN_CAN_BUILD=0
fi

if [ "$HDBSCAN_CAN_BUILD" -eq 0 ]; then
  REQ_TMP="$(mktemp)"
  filter_requirements_without_hdbscan "$REQ_BASE" "$REQ_TMP"
  REQ_INSTALL="$REQ_TMP"
fi

"$PYTHON_BIN" -m pip install -r "$REQ_INSTALL"

if [ "$HDBSCAN_CAN_BUILD" -eq 0 ]; then
  info "Installing hdbscan from wheel (if available)..."
  if "$PYTHON_BIN" -m pip install --only-binary=:all: --no-deps hdbscan; then
    info "hdbscan installed from wheel."
  else
    warn "hdbscan wheel not available for this platform/Python."
    warn "To build from source, install Python headers/build tools (run with --system-deps)."
    warn "Alternatively, use scripts/setup_host_conda.sh."
  fi
fi

if [ -n "$REQ_TMP" ]; then
  rm -f "$REQ_TMP"
fi

if [ "$GPU_DEPS" -eq 1 ]; then
  if [ ! -f "$REQ_GPU" ]; then
    die "Missing $REQ_GPU"
  fi
  CUDA_MAJOR="${CUDA_MAJOR:-12}"
  info "Installing GPU requirements (CUDA ${CUDA_MAJOR}.x)..."
  PIP_GPU_EXTRA=()
  if [ "$CUDA_MAJOR" = "12" ]; then
    CONSTRAINT_FILE="$SCRIPT_DIR/constraints-cuda12.txt"
    if [ -f "$CONSTRAINT_FILE" ]; then
      PIP_GPU_EXTRA=(-c "$CONSTRAINT_FILE")
      info "Using cuda-bindings constraint for torch compatibility (CUDA 12)."
    fi
  fi
  "$PYTHON_BIN" -m pip install -r "$REQ_GPU" --extra-index-url https://pypi.nvidia.com "${PIP_GPU_EXTRA[@]}"
  if [ "$CUDA_MAJOR" = "13" ]; then
    warn "CUDA 13.x: torch (e.g. from methylutils) requires cuda-bindings==12.9.4 and may conflict."
    warn "If you see a cuda-bindings conflict and need torch, use: pip install cuda-bindings==12.9.4"
  fi
  if ! install_nvrtc_system_deps "$CUDA_MAJOR"; then
    warn "CUDA NVRTC library (libnvrtc.so.${CUDA_MAJOR}) not detected."
    warn "On ARM64 systems, pip GPU wheels may omit NVRTC."
    warn "Install with: sudo apt-get install -y libnvrtc${CUDA_MAJOR} libnvrtc-builtins${CUDA_MAJOR}"
    warn "Or use: scripts/setup_host_conda.sh for a full CUDA toolchain."
    die "GPU dependencies incomplete (missing libnvrtc.so.${CUDA_MAJOR})."
  fi
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
  "methylpredictor"
  "methylvalidation"
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
