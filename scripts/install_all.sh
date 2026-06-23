#!/bin/bash
# Install all MethylPipeline packages in editable mode for development
# This script should be run inside the container

set -e

usage() {
    cat <<'EOF'
Usage: scripts/install_all.sh [options]

Options:
  --pipeline-reqs   Install pipeline-level Python requirements first
  --gpu-reqs        Install GPU requirements (CUDA 12 stack)
  --with-deps       Allow dependency resolution for local package installs
  --skip-marp       Skip Marp CLI installation
  -h, --help        Show this help

Notes:
  - requirements-pipeline.txt and requirements-gpu-cuda12.txt are expected at repo root.
EOF
}

PIPELINE_REQS=0
GPU_REQS=0
SKIP_MARP=0
WITH_DEPS=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pipeline-reqs) PIPELINE_REQS=1; shift ;;
        --gpu-reqs) GPU_REQS=1; shift ;;
        --with-deps) WITH_DEPS=1; shift ;;
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

# Ensure we run in the project virtualenv when available.
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.venv/bin/activate"
    echo "🐍 Activated virtualenv: $PROJECT_ROOT/.venv"
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

# Optional: install pipeline-level requirements
if [ "$PIPELINE_REQS" -eq 1 ] || [ "$GPU_REQS" -eq 1 ]; then
    echo "🔧 Upgrading pip tooling..."
    "$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel
fi

if [ "$PIPELINE_REQS" -eq 1 ]; then
    REQ_BASE="$PROJECT_ROOT/requirements-pipeline.txt"
    if [ -f "$REQ_BASE" ]; then
        echo "📦 Installing pipeline requirements..."
        "$PYTHON_BIN" -m pip install -r "$REQ_BASE"
    else
        echo "⚠ requirements-pipeline.txt not found at $REQ_BASE"
    fi
fi

if [ "$GPU_REQS" -eq 1 ]; then
    REQ_GPU="$PROJECT_ROOT/requirements-gpu-cuda12.txt"
    CONSTRAINT_GPU="$PROJECT_ROOT/scripts/constraints-cuda12.txt"
    if [ -f "$REQ_GPU" ]; then
        echo "🚀 Installing GPU requirements (CUDA12 profile)..."
        if [ -f "$CONSTRAINT_GPU" ]; then
            "$PYTHON_BIN" -m pip install -r "$REQ_GPU" -c "$CONSTRAINT_GPU" --extra-index-url https://pypi.nvidia.com
        else
            "$PYTHON_BIN" -m pip install -r "$REQ_GPU" --extra-index-url https://pypi.nvidia.com
        fi
    else
        echo "⚠ requirements-gpu-cuda12.txt not found at $REQ_GPU"
    fi
fi

# Install packages from canonical list (includes workers/)
# shellcheck source=install_packages.sh
source "$SCRIPT_DIR/install_packages.sh"
echo "📦 Installing packages from scripts/packages.list..."
install_packages_from_list "$PROJECT_ROOT" "$PYTHON_BIN" "$PACKAGES_DIR" "$WITH_DEPS"

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
    echo "   • methylextractionqc - Post-extraction QC guardrails (methyl-extraction-qc)"
echo "   • methylpredictor - Prediction and validation metrics (methyl-predictor)"
echo "   • methylvalidation - Monte Carlo validation workflows (methyl-validation)"
echo "   • methyldomain    - Domain program types and compiler helpers"
echo "   • methylfragmentomics - cfDNA fragmentomics (methyl-fragmentomics)"
echo "   • methyl-worker   - REST workflow worker (methyl-worker)"
echo "   • marp-cli        - Presentation rendering for docs/presentations/"
echo ""
echo "🧪 Test the installation:"
echo "   python -c \"from methyl_utils import get_logger; print('✓ MethylUtils OK')\""
echo "   python -c \"from methyl_detector import MethylDetector; print('✓ MethylDetector OK')\""
echo "   marp --version"
echo ""

