#!/bin/bash

# MethylCentroid Container Setup Script
# This script sets up MethylCentroid for container-only usage
# No heavy Python packages installed on the VM

set -e  # Exit on any error

echo "🐳 MethylCentroid Container Setup Script"
echo "=========================================="

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed or not available."
    echo "Please install Docker first."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: pyproject.toml not found. Please run this script from the MethylCentroid root directory."
    exit 1
fi

echo "🔧 Setting up MethylCentroid for container usage..."
echo "This will create wrapper scripts and verify container access."

# Check if epimethyl container exists and is running
if ! docker ps -a --format 'table {{.Names}}' | grep -q "^epimethyl$"; then
    echo "🔨 Building epimethyl container from ~/Work/cuda/docker-compose.yml..."

    # Check if docker-compose.yml exists
    if [ ! -f ~/Work/cuda/docker-compose.yml ]; then
        echo "❌ Error: ~/Work/cuda/docker-compose.yml not found."
        echo "Please ensure the CUDA environment setup is available."
        exit 1
    fi

    # Navigate to the cuda directory and build/start the container
    cd ~/Work/cuda

    # Build the image
    echo "Building epimethyl image..."
    if ! docker compose build gpu_env; then
        echo "❌ Error: Failed to build epimethyl image."
        exit 1
    fi

    # Start the container
    echo "Starting epimethyl container..."
    if ! docker compose up -d gpu_env; then
        echo "❌ Error: Failed to start epimethyl container."
        exit 1
    fi

    # Wait for container to be ready
    echo "Waiting for container to be ready..."
    sleep 5

    # Install packages in the container
    echo "Installing MethylCentroid and dependencies in container..."
    if ! docker exec epimethyl /home/ubuntu/Work/cuda/setup_methyl_packages.sh; then
        echo "❌ Error: Failed to install packages in container."
        exit 1
    fi

    # Return to original directory
    cd - > /dev/null

    echo "✅ epimethyl container built, started, and packages installed successfully!"
elif ! docker ps --format 'table {{.Names}}' | grep -q "^epimethyl$"; then
    echo "⚠️  epimethyl container exists but is not running."
    echo "Starting existing container..."

    # Start the container using docker compose
    if [ -f ~/Work/cuda/docker-compose.yml ]; then
        cd ~/Work/cuda
        docker compose up -d gpu_env
        cd - > /dev/null
    else
        echo "⚠️  Warning: ~/Work/cuda/docker-compose.yml not found."
        echo "Please start the epimethyl container manually."
    fi
fi

# Create a simple wrapper script for easy usage
cat > mc << 'EOF'
#!/bin/bash
# MethylCentroid Container Wrapper
# Usage: ./mc [args...]

if ! docker ps --format 'table {{.Names}}' | grep -q "^epimethyl$"; then
    echo "❌ Error: epimethyl container is not running."
    echo "Start it with: docker run -d --name epimethyl <your-image>"
    exit 1
fi

# Execute the command inside the container
exec docker exec -w /home/ubuntu/MethylCentroid epimethyl python -m methylcentroid.centroid_cli "$@"
EOF

chmod +x mc

echo "✅ Container setup completed successfully!"
echo ""
echo "🎯 Usage Instructions:"
echo "======================"
echo "1. Ensure epimethyl container is running:"
echo "   docker ps | grep epimethyl"
echo ""
echo "2. Use the wrapper script:"
echo "   ./mc --help"
echo "   ./mc --config your_config.json"
echo ""
echo "3. Or use Docker directly:"
echo "   docker exec -w /home/ubuntu/MethylCentroid epimethyl \\"
echo "     python -m methylcentroid.centroid_cli --config your_config.json"
echo ""
echo "📚 For more information, see README.md"
echo ""
echo "💡 Note: No heavy packages installed on VM - everything runs in container!"
