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
  -h, --help        Show this help

Notes:
  - requirements-pipeline.txt and requirements-gpu.txt are expected at repo root.
EOF
}

PIPELINE_REQS=0
GPU_REQS=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pipeline-reqs) PIPELINE_REQS=1; shift ;;
        --gpu-reqs) GPU_REQS=1; shift ;;
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

# Determine the base directory
if [ -d "/workspace/packages" ]; then
    PACKAGES_DIR="/workspace/packages"
elif [ -d "./packages" ]; then
    PACKAGES_DIR="./packages"
else
    echo "Error: Cannot find packages directory"
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
    "methyldetector"
    "methylmapper"
    "methylclassifier"
    "methylenricher"
    "methylcluster"
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
echo "============================================="
echo "✅ Package installation complete!"
echo "============================================="
echo ""
echo "📦 Installed packages:"
echo "   • methylutils     - Core utilities and GPU support (methyl_utils)"
echo "   • methylcentroid  - Centroid generation (methyl_centroid)"
echo "   • methyldetector  - DMP detection and model creation (methyl_detector)"
echo "   • methylmapper    - DMP-to-gene mapping (methyl-mapper)"
echo "   • methylclassifier - Sample classification (methyl-classifier)"
echo "   • methylenricher  - Gene enrichment analysis (methyl-enricher)"
echo "   • methylcluster   - HDBSCAN sample clustering (methyl_cluster)"
echo ""
echo "🧪 Test the installation:"
echo "   python -c \"from methyl_utils import get_logger; print('✓ MethylUtils OK')\""
echo "   python -c \"from methyl_detector import MethylDetector; print('✓ MethylDetector OK')\""
echo ""

