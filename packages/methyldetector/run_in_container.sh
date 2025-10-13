#!/bin/bash
# Script to run MethylDetector in the container with MethylUtils in the path

# Function to find MethylUtils path
find_methyl_utils() {
    # Check if METHYL_UTILS_PATH environment variable is set
    if [ -n "$METHYL_UTILS_PATH" ]; then
        if [ -d "$METHYL_UTILS_PATH" ]; then
            echo "$METHYL_UTILS_PATH"
            return 0
        else
            echo "Warning: METHYL_UTILS_PATH='$METHYL_UTILS_PATH' does not exist" >&2
        fi
    fi

    # Try default location (same level as MethylDetector)
    local default_path="/home/ubuntu/MethylUtils"
    if [ -d "$default_path" ]; then
        echo "$default_path"
        return 0
    fi

    # Try relative to current directory
    local relative_path="$(pwd)/../MethylUtils"
    if [ -d "$relative_path" ]; then
        echo "$relative_path"
        return 0
    fi

    # Try relative to script directory
    local script_dir="$(dirname "$0")"
    local script_relative="${script_dir}/../MethylUtils"
    if [ -d "$script_relative" ]; then
        echo "$script_relative"
        return 0
    fi

    # Try common system locations
    for common_path in \
        "/opt/methyl_utils" \
        "/usr/local/lib/methyl_utils" \
        "/usr/lib/methyl_utils"; do
        if [ -d "$common_path" ]; then
            echo "$common_path"
            return 0
        fi
    done

    return 1
}

# Find MethylUtils
METHYL_UTILS_PATH=$(find_methyl_utils)

if [ $? -eq 0 ] && [ -d "$METHYL_UTILS_PATH" ]; then
    echo "Found MethylUtils at: $METHYL_UTILS_PATH" >&2
    export PYTHONPATH="$METHYL_UTILS_PATH:$PYTHONPATH"
else
    echo "Warning: Could not find MethylUtils. Set METHYL_UTILS_PATH environment variable or ensure it's installed." >&2
    echo "Searched locations:" >&2
    echo "  - \$METHYL_UTILS_PATH (environment variable)" >&2
    echo "  - /home/ubuntu/MethylUtils (default)" >&2
    echo "  - ../MethylUtils (relative to cwd)" >&2
    echo "  - ../MethylUtils (relative to script)" >&2
    echo "  - /opt/methyl_utils" >&2
    echo "  - /usr/local/lib/methyl_utils" >&2
    echo "  - /usr/lib/methyl_utils" >&2
fi

# Run the command passed as arguments
exec "$@"
