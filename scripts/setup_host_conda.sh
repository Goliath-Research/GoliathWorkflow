#!/bin/bash
# Host environment setup script for CUDA 13.0 + RAPIDS (conda)

set -e

usage() {
    cat <<'EOF'
Usage: scripts/setup_host_conda.sh [options]

Options:
  --install-miniforge   Install Miniforge locally if conda is missing
  --miniforge-dir PATH  Install/use Miniforge at PATH (default: ~/.miniforge3)
  --rapids-version VER  RAPIDS meta version (default: 25.12)
  --init-shell          Add conda hook to shell rc for new shells
  --shell-rc PATH       Shell rc file to update (default: ~/.bashrc or ~/.zshrc)
  -h, --help            Show this help
EOF
}

MINIFORGE_DIR="${MINIFORGE_DIR:-$HOME/.miniforge3}"
INSTALL_MINIFORGE=0
RAPIDS_VERSION="${RAPIDS_VERSION:-25.12}"
INIT_SHELL=0
SHELL_RC=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-miniforge) INSTALL_MINIFORGE=1; shift ;;
        --miniforge-dir) MINIFORGE_DIR="${2:-}"; shift 2 ;;
        --rapids-version) RAPIDS_VERSION="${2:-}"; shift 2 ;;
        --init-shell) INIT_SHELL=1; shift ;;
        --shell-rc) SHELL_RC="${2:-}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "❌ Unknown option: $1"; usage; exit 1 ;;
    esac
done

if [ -z "$RAPIDS_VERSION" ]; then
    echo "❌ --rapids-version requires a value"
    exit 1
fi

detect_shell_rc() {
    if [ -n "$SHELL_RC" ]; then
        echo "$SHELL_RC"
        return 0
    fi
    case "${SHELL:-}" in
        */zsh) echo "$HOME/.zshrc" ;;
        */bash) echo "$HOME/.bashrc" ;;
        *) echo "$HOME/.bashrc" ;;
    esac
}

init_shell_rc() {
    local rc_file start_marker end_marker
    rc_file="$(detect_shell_rc)"
    start_marker="# >>> methylpipeline conda init >>>"
    end_marker="# <<< methylpipeline conda init <<<"

    if [ ! -f "$rc_file" ]; then
        touch "$rc_file"
    fi
    if grep -q "$start_marker" "$rc_file"; then
        echo "✅ Shell rc already configured: $rc_file"
        return 0
    fi

    cat >> "$rc_file" <<EOF
$start_marker
# Added by scripts/setup_host_conda.sh --init-shell
if [ -f "$MINIFORGE_DIR/etc/profile.d/conda.sh" ]; then
  . "$MINIFORGE_DIR/etc/profile.d/conda.sh"
fi
$end_marker
EOF
    echo "✅ Added conda init to: $rc_file"
}

run_installer() {
    local installer_path="$1"
    local prefix="$2"
    local output=""

    if output="$(env -i HOME="$HOME" PATH="$PATH" bash "$installer_path" -b -p "$prefix" 2>&1)"; then
        return 0
    fi

    if [[ "$output" == *"Please run using"* ]]; then
        echo "Installer reported it was sourced; retrying with sh..."
        if output="$(env -i HOME="$HOME" PATH="$PATH" sh "$installer_path" -b -p "$prefix" 2>&1)"; then
            return 0
        fi
    fi

    echo "$output"
    return 1
}

ensure_conda() {
    if command -v conda >/dev/null 2>&1; then
        return 0
    fi

    if [ -x "$MINIFORGE_DIR/bin/conda" ]; then
        export PATH="$MINIFORGE_DIR/bin:$PATH"
        return 0
    fi

    if [ "$INSTALL_MINIFORGE" -eq 0 ]; then
        echo "❌ Conda not found."
        echo "   Re-run with --install-miniforge or install Miniforge first:"
        echo "   https://github.com/conda-forge/miniforge"
        exit 1
    fi

    local arch installer url tmp installer_path cache_dir
    arch="$(uname -m)"
    case "$arch" in
        x86_64|amd64) installer="Miniforge3-Linux-x86_64.sh" ;;
        aarch64|arm64) installer="Miniforge3-Linux-aarch64.sh" ;;
        *)
            echo "❌ Unsupported architecture: $arch"
            exit 1
            ;;
    esac

    url="https://github.com/conda-forge/miniforge/releases/latest/download/${installer}"
    tmp="$(mktemp)"
    cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/methylpipeline"
    installer_path="$cache_dir/$installer"
    mkdir -p "$cache_dir"

    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$url" -o "$tmp"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$tmp" "$url"
    else
        echo "❌ curl or wget is required to download Miniforge."
        exit 1
    fi

    mv "$tmp" "$installer_path"
    chmod +x "$installer_path"
    run_installer "$installer_path" "$MINIFORGE_DIR"
    export PATH="$MINIFORGE_DIR/bin:$PATH"
}

echo "============================================="
echo "MethylPipeline Host Conda Setup"
echo "============================================="
echo ""

ensure_conda

if [ "$INIT_SHELL" -eq 1 ]; then
    init_shell_rc
fi

ENV_NAME="rapids-${RAPIDS_VERSION}"
ENV_PATH="$MINIFORGE_DIR/envs/$ENV_NAME"
CONDA_CHANNELS=(-c rapidsai-nightly -c conda-forge -c nvidia)

conda_env_action() {
    if [ -d "$ENV_PATH" ]; then
        echo "install"
    else
        echo "create"
    fi
}

conda_env_run() {
    local action
    action="$(conda_env_action)"
    if [ "$action" = "install" ]; then
        conda install -y -n "$ENV_NAME" "$@"
    else
        conda create -y -n "$ENV_NAME" "$@"
    fi
}

echo "🐍 Creating conda environment: $ENV_NAME"
if ! conda_env_run "${CONDA_CHANNELS[@]}" \
  "rapidsai-nightly::rapids=${RAPIDS_VERSION}" python=3.12 'cuda-version=13.0' \
  jupyter hdbscan umap-learn; then
    echo "⚠️  RAPIDS ${RAPIDS_VERSION} not available for this platform."
    echo "   Falling back to latest RAPIDS from rapidsai-nightly..."
    conda_env_run "${CONDA_CHANNELS[@]}" \
      "rapidsai-nightly::rapids" python=3.12 'cuda-version=13.0' \
      jupyter hdbscan umap-learn
fi

echo "📦 Installing additional libraries..."
EXTRA_PACKAGES=(
  h5py hdf5plugin zarr pyarrow psutil plotly matplotlib seaborn
  click tqdm statsmodels sqlalchemy scikit-learn pydantic pyodbc pymssql
)

ARCH="$(uname -m)"
if [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
    echo "⚠️  pymssql not available on conda-forge for ${ARCH}; skipping."
    FILTERED_PACKAGES=()
    for pkg in "${EXTRA_PACKAGES[@]}"; do
        if [ "$pkg" != "pymssql" ]; then
            FILTERED_PACKAGES+=("$pkg")
        fi
    done
    EXTRA_PACKAGES=("${FILTERED_PACKAGES[@]}")
fi

if [ "${#EXTRA_PACKAGES[@]}" -gt 0 ]; then
    conda install -y -n "$ENV_NAME" -c conda-forge "${EXTRA_PACKAGES[@]}"
fi

echo "✅ Conda environment ready."
echo ""
echo "Next steps:"
echo "  conda activate $ENV_NAME"
echo "If conda is not found in a new shell, run:"
echo "  source \"$MINIFORGE_DIR/etc/profile.d/conda.sh\""
echo "Or rerun this script with --init-shell to add conda to your shell rc."
echo "  pip install -e packages/methylutils --no-deps"
echo "  pip install -e packages/methylcentroid --no-deps"
echo "  pip install -e packages/methyldetector --no-deps"
echo "  pip install -e packages/methylmapper --no-deps"
echo "  pip install -e packages/methylclassifier --no-deps"
echo "  pip install -e packages/methylenricher --no-deps"
echo "  pip install -e packages/methylcluster --no-deps"
echo ""
