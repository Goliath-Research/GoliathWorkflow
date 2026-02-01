#!/bin/bash
# MethylPipeline Environment Setup
# Source this file to set up the MethylPipeline environment
# Usage: source setup_env.sh

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

append_ld_library_path() {
    local dir="$1"
    if [ -z "$dir" ]; then
        return 0
    fi
    case ":${LD_LIBRARY_PATH:-}:" in
        *":${dir}:"*) return 0 ;;
        *) export LD_LIBRARY_PATH="${dir}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" ;;
    esac
}

add_nvrtc_lib_dir() {
    local dir="$1"
    if compgen -G "${dir}/libnvrtc.so*" > /dev/null; then
        append_ld_library_path "$dir"
        return 0
    fi
    return 1
}

add_system_nvrtc_libs() {
    local dir
    local added=0

    for dir in /usr/lib/aarch64-linux-gnu /usr/lib/x86_64-linux-gnu /usr/lib /usr/local/cuda/lib64; do
        if [ -d "$dir" ] && add_nvrtc_lib_dir "$dir"; then
            added=1
        fi
    done

    for dir in /usr/local/cuda/targets/*/lib /usr/local/cuda-*/targets/*/lib; do
        if [ -d "$dir" ] && add_nvrtc_lib_dir "$dir"; then
            added=1
        fi
    done

    if [ "$added" -eq 1 ] && [ -z "${CUDA_PATH:-}" ]; then
        if [ -d "/usr/local/cuda" ]; then
            export CUDA_PATH="/usr/local/cuda"
        fi
    fi
}

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
            if [ -d "${NVRTC_LIB}" ] && compgen -G "${NVRTC_LIB}/libnvrtc.so*" > /dev/null; then
                append_ld_library_path "${NVRTC_LIB}"
                if [ -d "${CUDART_LIB}" ]; then
                    append_ld_library_path "${CUDART_LIB}"
                fi
                export CUDA_PATH="${CUDA_PATH:-${SITE_PACKAGES}/nvidia/cuda_runtime}"
            fi
        fi
    fi
    add_system_nvrtc_libs

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
            if [ -d "${NVRTC_LIB}" ] && compgen -G "${NVRTC_LIB}/libnvrtc.so*" > /dev/null; then
                append_ld_library_path "${NVRTC_LIB}"
                if [ -d "${CUDART_LIB}" ]; then
                    append_ld_library_path "${CUDART_LIB}"
                fi
                export CUDA_PATH="${CUDA_PATH:-${SITE_PACKAGES}/nvidia/cuda_runtime}"
            fi
        fi
    fi
    add_system_nvrtc_libs
    
    echo "✅ Local development environment configured."
    echo ""
    echo "🐳 To manage the Docker environment:"
    echo "   Build: ${SCRIPT_DIR}/scripts/manage_docker.sh build"
    echo "   Start: ${SCRIPT_DIR}/scripts/manage_docker.sh start"
    echo "   Stop:  ${SCRIPT_DIR}/scripts/manage_docker.sh stop"
    echo ""
fi

