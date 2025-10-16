#!/bin/bash

# MethylCentroid Local Installation Script
# This script installs MethylCentroid with local MethylUtils dependencies
# ⚠️  WARNING: This installs heavy Python packages on your VM!
# For container usage, use ./install.sh instead (recommended)

set -e  # Exit on any error

echo "⚠️  WARNING: This will install heavy Python packages on your VM!"
echo "For container-only usage (recommended), use ./install.sh instead."
echo ""
read -p "Continue with local installation? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled. Use ./install.sh for container setup."
    exit 0
fi

echo "🏠 MethylCentroid Local Installation Script"
echo "============================================"

# Check if Poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "📦 Installing Poetry..."
    pip install poetry
else
    echo "✅ Poetry is already installed"
fi

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: pyproject.toml not found. Please run this script from the MethylCentroid root directory."
    exit 1
fi

# Check if MethylUtils is available locally
if [ ! -d "../MethylUtils" ]; then
    echo "❌ Error: MethylUtils not found at ../MethylUtils"
    echo "Please ensure MethylUtils is available in the parent directory, or use the regular install.sh script."
    exit 1
fi

echo "🔧 Installing MethylCentroid with local MethylUtils dependencies..."

# Create a backup of the original pyproject.toml
cp pyproject.toml pyproject.toml.backup

# First, install the local methyl-utils package
echo "📦 Installing local MethylUtils package..."
cd ../MethylUtils
pip install -e .
cd ../MethylCentroid

# Temporarily move pyproject.toml so pip uses setup.py instead
echo "📝 Temporarily moving pyproject.toml to use setup.py..."
mv pyproject.toml pyproject.toml.temp

# Install MethylCentroid using setup.py
echo "📦 Installing MethylCentroid using setup.py..."
pip install -e .

# Restore the original pyproject.toml (with git dependencies)
echo "🔄 Restoring original pyproject.toml..."
mv pyproject.toml.temp pyproject.toml

# Install development dependencies if requested
if [ "$1" = "--dev" ] || [ "$1" = "-d" ]; then
    echo "📦 Installing development dependencies..."
    pip install pytest pytest-cov black flake8 mypy pre-commit
fi

echo "✅ Local installation completed successfully!"
echo ""
echo "🎯 Usage Instructions:"
echo "======================"
echo "1. Activate the Poetry environment:"
echo "   poetry shell"
echo ""
echo "2. Verify installation:"
echo "   python -c \"import methyl_centroid; print('MethylCentroid ready!')\""
echo ""
echo "3. Run analysis with Docker container:"
echo "   docker exec -w /home/ubuntu/MethylCentroid epimethyl \\"
echo "     python -m methylcentroid.centroid_cli --config your_config.json"
echo ""
echo "📚 For more information, see README.md"
echo ""
echo "⚠️  Note: This installation uses local MethylUtils. If you need to update"
echo "   MethylUtils, you may need to reinstall MethylCentroid."
