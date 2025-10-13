#!/bin/bash
# Container launcher script
# Quick script to start/stop containers

set -e

# Get the script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Default to development
MODE="${1:-dev}"

if [ "$MODE" == "dev" ]; then
    COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.yml"
    CONTAINER_NAME="methylpipeline"
elif [ "$MODE" == "prod" ]; then
    COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.production.yml"
    CONTAINER_NAME="methylpipeline-prod"
else
    echo "Usage: $0 [dev|prod]"
    echo "  dev  - Run development container (default)"
    echo "  prod - Run production container"
    exit 1
fi

ACTION="${2:-start}"

case "$ACTION" in
    start)
        echo "🚀 Starting $MODE container..."
        cd "$PROJECT_ROOT/docker"
        docker compose -f "$(basename $COMPOSE_FILE)" up -d
        echo "✅ Container started: $CONTAINER_NAME"
        echo "   Attach: docker exec -it $CONTAINER_NAME bash"
        ;;
    stop)
        echo "🛑 Stopping $MODE container..."
        cd "$PROJECT_ROOT/docker"
        docker compose -f "$(basename $COMPOSE_FILE)" down
        echo "✅ Container stopped"
        ;;
    restart)
        echo "🔄 Restarting $MODE container..."
        cd "$PROJECT_ROOT/docker"
        docker compose -f "$(basename $COMPOSE_FILE)" restart
        echo "✅ Container restarted: $CONTAINER_NAME"
        ;;
    logs)
        cd "$PROJECT_ROOT/docker"
        docker compose -f "$(basename $COMPOSE_FILE)" logs -f
        ;;
    shell)
        docker exec -it $CONTAINER_NAME bash
        ;;
    *)
        echo "Usage: $0 [dev|prod] [start|stop|restart|logs|shell]"
        echo ""
        echo "Modes:"
        echo "  dev  - Development container (default)"
        echo "  prod - Production container"
        echo ""
        echo "Actions:"
        echo "  start   - Start container (default)"
        echo "  stop    - Stop container"
        echo "  restart - Restart container"
        echo "  logs    - View container logs"
        echo "  shell   - Open bash shell in container"
        exit 1
        ;;
esac

