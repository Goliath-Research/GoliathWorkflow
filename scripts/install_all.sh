#!/bin/bash
# Install all MethylPipeline packages in editable mode for development
# This script should be run inside the container

set -e

usage() {
    cat <<'EOF'
Usage: scripts/install_all.sh [options]

Options:
  --pipeline-reqs   Install pipeline-level Python requirements first
  --gpu-reqs        Install GPU requirements (CUDA 13.x stack)
  --skip-marp       Skip Marp CLI installation
  -h, --help        Show this help

Notes:
  - requirements-pipeline.txt and requirements-gpu.txt are expected at repo root.
EOF
}

PIPELINE_REQS=0
GPU_REQS=0
SKIP_MARP=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pipeline-reqs) PIPELINE_REQS=1; shift ;;
        --gpu-reqs) GPU_REQS=1; shift ;;
        --skip-marp) SKIP_MARP=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "============================================="
echo "Installing MethylPipeline Packages..."
echo "============================================="
echo ""

# Determine the base directory (prefer this repository checkout)
if [ -d "$PROJECT_ROOT/packages" ]; then
    PACKAGES_DIR="$PROJECT_ROOT/packages"
elif [ -d "./packages" ]; then
    PACKAGES_DIR="./packages"
elif [ -d "/workspace/packages" ]; then
    PACKAGES_DIR="/workspace/packages"
else
    echo "Error: Cannot find packages directory"
    echo "Checked: $PROJECT_ROOT/packages, ./packages, /workspace/packages"
    exit 1
fi

echo "📦 Installing packages from: $PACKAGES_DIR"
echo ""

# Optional: install pipeline-level requirements
if [ "$PIPELINE_REQS" -eq 1 ] || [ "$GPU_REQS" -eq 1 ]; then
    echo "🔧 Upgrading pip tooling..."
    python3 -m pip install --upgrade pip setuptools wheel
fi

if [ "$PIPELINE_REQS" -eq 1 ]; then
    REQ_BASE="$PROJECT_ROOT/requirements-pipeline.txt"
    if [ -f "$REQ_BASE" ]; then
        echo "📦 Installing pipeline requirements..."
        python3 -m pip install -r "$REQ_BASE"
    else
        echo "⚠ requirements-pipeline.txt not found at $REQ_BASE"
    fi
fi

if [ "$GPU_REQS" -eq 1 ]; then
    REQ_GPU="$PROJECT_ROOT/requirements-gpu.txt"
    if [ -f "$REQ_GPU" ]; then
        echo "🚀 Installing GPU requirements..."
        python3 -m pip install -r "$REQ_GPU" --extra-index-url https://pypi.nvidia.com
    else
        echo "⚠ requirements-gpu.txt not found at $REQ_GPU"
    fi
fi

# Install packages in dependency order
# MethylUtils must be installed first as it's the core dependency
PACKAGES=(
    "methylutils"
    "methylcentroid"
    "methylcluster"
    "methyldetector"
    "methylmapper"
    "methylclassifier"
    "methylenricher"
    "methyldiseaseprogression"
    "methylalignmentqc"
    "methylpredictor"
    "methylvalidation"
)

for pkg in "${PACKAGES[@]}"; do
    PKG_PATH="$PACKAGES_DIR/$pkg"
    if [ -d "$PKG_PATH" ]; then
        if [ -f "$PKG_PATH/pyproject.toml" ]; then
            echo "📦 Installing $pkg..."
            cd "$PKG_PATH"
            if [ -n "${CONDA_DEFAULT_ENV:-}" ]; then
                echo "   • Detected conda env (${CONDA_DEFAULT_ENV}), installing without dependency resolution"
                python -m pip install -e . --no-deps --no-cache-dir 2>&1 | grep -v "WARNING"
            else
                # Use poetry install for proper dependency management
                # Use full path to poetry if not in PATH
                if command -v poetry &> /dev/null; then
                    poetry install --no-interaction --no-ansi 2>&1 | grep -v "Creating virtualenv"
                elif [ -f /root/.local/bin/poetry ]; then
                    /root/.local/bin/poetry install --no-interaction --no-ansi 2>&1 | grep -v "Creating virtualenv"
                elif [ -f /usr/local/bin/poetry ]; then
                    /usr/local/bin/poetry install --no-interaction --no-ansi 2>&1 | grep -v "Creating virtualenv"
                else
                    echo "   ⚠ Poetry not found, trying pip install as fallback..."
                    python3 -m pip install -e . --no-cache-dir 2>&1 | grep -v "WARNING"
                fi
            fi
            echo "   ✓ $pkg installed"
        else
            echo "   ⚠ Skipping $pkg (missing pyproject.toml)"
        fi
    else
        echo "   ⚠ Skipping $pkg (directory not found)"
    fi
done

echo ""
echo "🖼️ Presentation tooling..."
if [ "$SKIP_MARP" -eq 1 ]; then
    echo "   • Skipping Marp installation (--skip-marp)"
else
    if command -v npm >/dev/null 2>&1; then
        echo "   • Installing Marp CLI via npm (global)..."
        if npm install -g @marp-team/marp-cli; then
            NPM_GLOBAL_BIN="$(npm config get prefix)/bin"
        else
            echo "   ⚠ Global npm install failed. Falling back to user-local npm prefix..."
            USER_NPM_PREFIX="${HOME}/.npm-global"
            ORIGINAL_NPM_PREFIX="$(npm config get prefix)"
            mkdir -p "$USER_NPM_PREFIX"
            npm config set prefix "$USER_NPM_PREFIX"
            if npm install -g @marp-team/marp-cli; then
                NPM_GLOBAL_BIN="${USER_NPM_PREFIX}/bin"
                echo "   ✓ Marp installed with user prefix: $USER_NPM_PREFIX"
                echo "     Add this to your shell profile if needed:"
                echo "       export PATH=\"$USER_NPM_PREFIX/bin:\$PATH\""
            else
                echo "   ⚠ Marp installation failed in both global and user-local modes."
                echo "   • Restoring original npm prefix: $ORIGINAL_NPM_PREFIX"
                npm config set prefix "$ORIGINAL_NPM_PREFIX" || true
                NPM_GLOBAL_BIN="$(npm config get prefix)/bin"
            fi
        fi
        if ! command -v marp >/dev/null 2>&1 && [ -x "$NPM_GLOBAL_BIN/marp" ]; then
            export PATH="$NPM_GLOBAL_BIN:$PATH"
        fi
        if command -v marp >/dev/null 2>&1; then
            echo "   ✓ Marp installed: $(marp --version)"
        else
            echo "   ⚠ Marp installation completed but 'marp' is not on PATH"
            echo "     Add this to your shell profile: export PATH=\"\$(npm config get prefix)/bin:\$PATH\""
        fi
    else
        echo "   ⚠ npm not found; Marp CLI was not installed."
        echo "     Install Node.js/npm, then run: npm install -g @marp-team/marp-cli"
    fi
fi

echo ""
echo "============================================="
echo "✅ Package installation complete!"
echo "============================================="
echo ""
echo "📦 Installed packages:"
echo "   • methylutils     - Core utilities and GPU support (methyl_utils)"
echo "   • methylcentroid  - Centroid generation (methyl_centroid)"
echo "   • methylcluster   - Sample clustering and subgroup discovery (methyl_cluster)"
echo "   • methyldetector  - DMP detection and model creation (methyl_detector)"
echo "   • methylmapper    - DMP-to-gene mapping (methyl-mapper)"
echo "   • methylclassifier - Sample classification (methyl-classifier)"
echo "   • methylenricher  - Gene enrichment analysis (methyl-enricher)"
echo "   • methyldiseaseprogression - Cross-stage progression synthesis (methyl-disease-progression)"
echo "   • methylalignmentqc - Alignment QC extraction (methyl-qc)"
echo "   • methylpredictor - Prediction and validation metrics (methyl-predictor)"
echo "   • methylvalidation - Monte Carlo validation workflows (methyl-validation)"
echo "   • marp-cli        - Presentation rendering for docs/presentations/"
echo ""
echo "🧪 Test the installation:"
echo "   python -c \"from methyl_utils import get_logger; print('✓ MethylUtils OK')\""
echo "   python -c \"from methyl_detector import MethylDetector; print('✓ MethylDetector OK')\""
echo "   marp --version"
echo ""

