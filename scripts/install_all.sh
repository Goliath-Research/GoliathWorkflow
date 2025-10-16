#!/bin/bash
# Install all MethylPipeline packages in editable mode for development
# This script should be run inside the container

set -e

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

# Install packages in dependency order
# MethylUtils must be installed first as it's the core dependency
PACKAGES=(
    "methylutils"
    "methylcentroid"
    "methyldetector"
    "methylmapper"
    "methyltrainer"
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
echo "   • methyldetector  - DMP detection with effect_size (methyl_detector)"
echo "   • methylmapper    - DMP-to-gene mapping (methyl_mapper)"
echo "   • methyltrainer   - Model training (methyl_trainer)"
echo "   • methylclassifier - Sample classification (methyl_classifier)"
echo "   • methylenricher  - Gene enrichment analysis (methyl_enricher)"
echo "   • methylcluster   - HDBSCAN sample clustering (methyl_cluster)"
echo ""
echo "🧪 Test the installation:"
echo "   python -c \"from methyl_utils import get_logger; print('✓ MethylUtils OK')\""
echo "   python -c \"from methyl_detector import MethylDetector; print('✓ MethylDetector OK')\"" 
echo ""

