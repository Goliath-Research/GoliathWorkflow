#!/bin/bash
# Wrapper script to install all MethylPipeline packages
# This script checks if the container is running and executes install_all.sh inside it

set -e

echo "============================================="
echo "MethylPipeline Package Installer"
echo "============================================="
echo ""

# Check if container is running
if ! docker ps --format 'table {{.Names}}' | grep -q "^methylpipeline$"; then
    echo "❌ Error: methylpipeline container is not running."
    echo ""
    echo "To start the container:"
    echo "  cd /home/ubuntu/MethylPipeline/docker"
    echo "  docker compose up -d"
    echo ""
    exit 1
fi

echo "✓ Container is running"
echo ""
echo "Installing packages inside the methylpipeline container..."
echo "This may take a few minutes..."
echo ""

# Execute install_all.sh inside the container
docker exec -w /workspace methylpipeline bash /workspace/scripts/install_all.sh

echo ""
echo "============================================="
echo "✅ Installation complete!"
echo "============================================="
echo ""
echo "You can now use the CLI wrappers:"
echo "  ./packages/methylmodeler/modeler config.json"
echo "  ./packages/methylcentroid/mc config.json"
echo "  ./packages/methylmapper/mm --help"
echo ""

