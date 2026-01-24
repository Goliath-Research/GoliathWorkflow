#!/bin/bash
# MethylPipeline Docker Manager
# Handles building and running the Docker environment with ARM64/GDX support

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$ROOT_DIR/docker"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}MethylPipeline Docker Manager${NC}"

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: docker is not installed.${NC}"
    exit 1
fi

# Determine if we need sudo
DOCKER_CMD="docker"
if ! docker info &> /dev/null; then
    echo -e "${YELLOW}Docker permission denied. Attempting to use sudo...${NC}"
    # Verify sudo is available
    if command -v sudo &> /dev/null; then
        DOCKER_CMD="sudo docker"
    else
        echo -e "${RED}Error: Docker requires permissions and sudo is not available.${NC}"
        echo -e "Please add your user to the docker group: sudo usermod -aG docker \$USER"
        exit 1
    fi
fi

# Detect Architecture
ARCH=$(uname -m)
echo -e "Detected architecture: ${YELLOW}${ARCH}${NC}"

# Check for NVIDIA components
if command -v nvidia-smi &> /dev/null; then
    echo -e "NVIDIA Driver: ${GREEN}Detected${NC}"
else
    echo -e "NVIDIA Driver: ${YELLOW}Not Detected (GPU support may be limited)${NC}"
fi

# Function to build
build_container() {
    echo -e "Building container..."
    cd "$DOCKER_DIR"
    
    # Pass architecture-specific build args if needed in future
    # Currently handled by pip config in Dockerfile
    
    $DOCKER_CMD compose build
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Build successful.${NC}"
    else
        echo -e "${RED}Build failed.${NC}"
        exit 1
    fi
}

# Function to run
run_container() {
    echo -e "Starting container..."
    cd "$DOCKER_DIR"
    
    $DOCKER_CMD compose up -d
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Container started.${NC}"
        echo -e "To access the shell: ${YELLOW}$DOCKER_CMD compose exec gpu_env bash${NC}"
    else
        echo -e "${RED}Failed to start container.${NC}"
        exit 1
    fi
}

# Main logic
case "$1" in
    build)
        build_container
        ;;
    up|run|start)
        run_container
        ;;
    down|stop)
        cd "$DOCKER_DIR" && $DOCKER_CMD compose down
        echo -e "${GREEN}Container stopped.${NC}"
        ;;
    restart)
        cd "$DOCKER_DIR" && $DOCKER_CMD compose down
        run_container
        ;;
    *)
        echo "Usage: $0 {build|start|stop|restart}"
        exit 1
        ;;
esac
