#!/bin/bash
# Production environment setup script
# Builds production container with packages installed

set -e

echo "============================================="
echo "MethylPipeline Production Setup"
echo "============================================="
echo ""

# Get the script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "📁 Project root: $PROJECT_ROOT"
echo ""

# Navigate to docker directory
cd "$PROJECT_ROOT/docker"

echo "🐋 Building production container..."
echo "⚠️  This will install all packages inside the container (non-editable)"
docker compose -f docker-compose.production.yml build

echo ""
echo "🚀 Starting production container..."
docker compose -f docker-compose.production.yml up -d

echo ""
echo "⏳ Waiting for container to be ready..."
sleep 5

echo ""
echo "🧪 Testing production installation..."
docker exec methylpipeline-prod python3 -c "from methyl_utils import get_logger; print('✓ Production container verified')" || {
    echo "❌ Production container verification failed"
    exit 1
}

echo ""
echo "✅ Production environment setup complete!"
echo ""
echo "📋 Container details:"
echo "   • Container name: methylpipeline-prod"
echo "   • Image: methylpipeline-gpu-env:production"
echo "   • Packages installed at: /opt/methylpipeline/lib/python3.10/site-packages"
echo ""
echo "🛠️  Useful commands:"
echo "   • Attach to container: docker exec -it methylpipeline-prod bash"
echo "   • View logs: docker compose -f $PROJECT_ROOT/docker/docker-compose.production.yml logs -f"
echo "   • Stop container: docker compose -f $PROJECT_ROOT/docker/docker-compose.production.yml down"
echo ""

