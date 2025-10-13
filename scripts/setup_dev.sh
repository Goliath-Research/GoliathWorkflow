#!/bin/bash
# Development environment setup script
# Builds container and sets up development environment

set -e

echo "============================================="
echo "MethylPipeline Development Setup"
echo "============================================="
echo ""

# Get the script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "📁 Project root: $PROJECT_ROOT"
echo ""

# Navigate to docker directory
cd "$PROJECT_ROOT/docker"

echo "🐋 Building development container..."
docker compose -f docker-compose.yml build

echo ""
echo "🚀 Starting container..."
docker compose -f docker-compose.yml up -d

echo ""
echo "⏳ Waiting for container to be ready..."
sleep 5

echo ""
echo "📦 Installing packages in development mode..."
docker exec methylpipeline bash -c "cd /workspace && bash scripts/install_all.sh"

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Attach to container: docker exec -it methylpipeline bash"
echo "   2. Test imports: python -c \"from methyl_utils import get_logger; print('OK')\""
echo "   3. Start developing!"
echo ""
echo "🛠️  Useful commands:"
echo "   • View logs: docker compose -f $PROJECT_ROOT/docker/docker-compose.yml logs -f"
echo "   • Stop container: docker compose -f $PROJECT_ROOT/docker/docker-compose.yml down"
echo "   • Restart container: docker compose -f $PROJECT_ROOT/docker/docker-compose.yml restart"
echo ""

