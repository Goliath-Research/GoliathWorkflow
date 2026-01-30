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

    # Add CUDA libraries from pip-installed NVIDIA wheels (if present)
    if [ -d "${METHYLPIPELINE}/.venv" ]; then
        for PY_LIB in "${METHYLPIPELINE}"/.venv/lib/python*; do
            if [ -d "${PY_LIB}/site-packages" ]; then
                SITE_PACKAGES="${PY_LIB}/site-packages"
                break
            fi
        done
        if [ -n "${SITE_PACKAGES:-}" ]; then
            NVRTC_LIB="${SITE_PACKAGES}/nvidia/cuda_nvrtc/lib"
            CUDART_LIB="${SITE_PACKAGES}/nvidia/cuda_runtime/lib"
            if [ -d "${NVRTC_LIB}" ]; then
                export LD_LIBRARY_PATH="${NVRTC_LIB}${CUDART_LIB:+:${CUDART_LIB}}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
                export CUDA_PATH="${CUDA_PATH:-${SITE_PACKAGES}/nvidia/cuda_runtime}"
            fi
        fi
    fi

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

    # Add CUDA libraries from pip-installed NVIDIA wheels (if present)
    if [ -d "${METHYLPIPELINE}/.venv" ]; then
        for PY_LIB in "${METHYLPIPELINE}"/.venv/lib/python*; do
            if [ -d "${PY_LIB}/site-packages" ]; then
                SITE_PACKAGES="${PY_LIB}/site-packages"
                break
            fi
        done
        if [ -n "${SITE_PACKAGES:-}" ]; then
            NVRTC_LIB="${SITE_PACKAGES}/nvidia/cuda_nvrtc/lib"
            CUDART_LIB="${SITE_PACKAGES}/nvidia/cuda_runtime/lib"
            if [ -d "${NVRTC_LIB}" ]; then
                export LD_LIBRARY_PATH="${NVRTC_LIB}${CUDART_LIB:+:${CUDART_LIB}}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
                export CUDA_PATH="${CUDA_PATH:-${SITE_PACKAGES}/nvidia/cuda_runtime}"
            fi
        fi
    fi
    
    echo "✅ Local development environment configured."
    echo ""
    echo "🐳 To manage the Docker environment:"
    echo "   Build: ${SCRIPT_DIR}/scripts/manage_docker.sh build"
    echo "   Start: ${SCRIPT_DIR}/scripts/manage_docker.sh start"
    echo "   Stop:  ${SCRIPT_DIR}/scripts/manage_docker.sh stop"
    echo ""
fi

