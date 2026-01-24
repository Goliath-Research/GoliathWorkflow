#!/bin/bash
# MethylPipeline Environment Setup
# Source this file to set up the MethylPipeline environment
# Usage: source setup_env.sh

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if we are running inside the Docker container
if [ -f "/.dockerenv" ] || [ -f "/run/.containerenv" ]; then
    # INSIDE DOCKER (or Container)
    
    # Set METHYLPIPELINE to the root directory
    export METHYLPIPELINE="$SCRIPT_DIR"

    # Add packages to PYTHONPATH
    export PYTHONPATH="${METHYLPIPELINE}/packages/methylutils:${METHYLPIPELINE}/packages/methylcentroid:${PYTHONPATH}"

    # Display confirmation
    echo "✅ MethylPipeline environment configured (Container Mode):"
    echo "   METHYLPIPELINE=${METHYLPIPELINE}"
    echo "   PYTHONPATH includes:"
    echo "     - ${METHYLPIPELINE}/packages/methylutils"
    echo "     - ${METHYLPIPELINE}/packages/methylcentroid"
    echo ""
    echo "Available projects:"
    echo "   - methylutils:    ${METHYLPIPELINE}/packages/methylutils"
    echo "   - methylcentroid: ${METHYLPIPELINE}/packages/methylcentroid"

else
    # OUTSIDE DOCKER (Host)
    
    echo "⚠️  You are running on the Host machine."
    echo "   For full GPU/RAPIDS support, you should run inside the Docker container."
    echo ""
    
    # Offer to setup local environment anyway for development convenience
    export METHYLPIPELINE="$SCRIPT_DIR"
    export PYTHONPATH="${METHYLPIPELINE}/packages/methylutils:${METHYLPIPELINE}/packages/methylcentroid:${PYTHONPATH}"
    
    echo "✅ Local development environment configured."
    echo ""
    echo "🐳 To manage the Docker environment:"
    echo "   Build: ${SCRIPT_DIR}/scripts/manage_docker.sh build"
    echo "   Start: ${SCRIPT_DIR}/scripts/manage_docker.sh start"
    echo "   Stop:  ${SCRIPT_DIR}/scripts/manage_docker.sh stop"
    echo ""
fi

