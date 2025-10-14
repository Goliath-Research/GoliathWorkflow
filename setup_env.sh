#!/bin/bash
# MethylPipeline Environment Setup
# Source this file to set up the MethylPipeline environment
# Usage: source setup_env.sh

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Set METHYLPIPELINE to the root directory
export METHYLPIPELINE="$SCRIPT_DIR"

# Add packages to PYTHONPATH
export PYTHONPATH="${METHYLPIPELINE}/packages/methylutils:${METHYLPIPELINE}/packages/methylcentroid:${PYTHONPATH}"

# Display confirmation
echo "✅ MethylPipeline environment configured:"
echo "   METHYLPIPELINE=${METHYLPIPELINE}"
echo "   PYTHONPATH includes:"
echo "     - ${METHYLPIPELINE}/packages/methylutils"
echo "     - ${METHYLPIPELINE}/packages/methylcentroid"
echo ""
echo "Available projects:"
echo "   - methylutils:    ${METHYLPIPELINE}/packages/methylutils"
echo "   - methylcentroid: ${METHYLPIPELINE}/packages/methylcentroid"

