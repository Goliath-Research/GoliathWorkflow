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
)

for pkg in "${PACKAGES[@]}"; do
    PKG_PATH="$PACKAGES_DIR/$pkg"
    if [ -d "$PKG_PATH" ]; then
        if [ -f "$PKG_PATH/setup.py" ] || [ -f "$PKG_PATH/pyproject.toml" ]; then
            echo "📦 Installing $pkg..."
            cd "$PKG_PATH"
            pip install -e . --quiet
            echo "   ✓ $pkg installed"
        else
            echo "   ⚠ Skipping $pkg (missing setup.py or pyproject.toml)"
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
echo "   • methylutils    - Core utilities and GPU support"
echo "   • methylcentroid - Centroid generation"
echo "   • methyldetector - DMP detection with effect_size"
echo "   • methylmapper   - DMP-to-gene mapping (Azure SQL)"
echo "   • methyltrainer  - Model training"
echo "   • methylclassifier - Sample classification"
echo "   • methylenricher - Gene enrichment analysis"
echo ""
echo "🧪 Test the installation:"
echo "   python -c \"from methyl_utils import get_logger; print('✓ MethylUtils OK')\""
echo ""

