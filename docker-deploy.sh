#!/bin/bash
set -e

# Docker deployment script
# Usage: ./docker-deploy.sh [environment]

ENVIRONMENT="${1:-production}"
COMPOSE_FILE="docker-compose.${ENVIRONMENT}.yml"

echo "========================================="
echo "Deploying to ${ENVIRONMENT} environment"
echo "========================================="

# Check if compose file exists
if [ ! -f "${COMPOSE_FILE}" ]; then
  echo "Error: ${COMPOSE_FILE} not found!"
  echo "Available environments:"
  ls docker-compose*.yml 2>/dev/null || echo "No docker-compose files found"
  exit 1
fi

# Load environment variables
if [ -f ".env.${ENVIRONMENT}" ]; then
  echo "Loading environment variables from .env.${ENVIRONMENT}"
  export $(cat ".env.${ENVIRONMENT}" | grep -v '^#' | xargs)
elif [ -f ".env" ]; then
  echo "Loading environment variables from .env"
  export $(cat ".env" | grep -v '^#' | xargs)
else
  echo "Warning: No .env file found"
fi

# Check required environment variables
REQUIRED_VARS=("REDIS_PASSWORD")
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var}" ]; then
    echo "Error: ${var} is not set!"
    exit 1
  fi
done

# Pull latest images
echo "Pulling latest images..."
docker-compose -f "${COMPOSE_FILE}" pull

# Stop and remove old containers
echo "Stopping old containers..."
docker-compose -f "${COMPOSE_FILE}" down --remove-orphans

# Start services
echo "Starting services..."
docker-compose -f "${COMPOSE_FILE}" up -d

# Wait for services to be healthy
echo "Waiting for services to be healthy..."
sleep 10

# Check service status
echo "========================================="
echo "Service Status:"
echo "========================================="
docker-compose -f "${COMPOSE_FILE}" ps

# Check application health
echo "========================================="
echo "Health Check:"
echo "========================================="
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  if curl -f http://localhost/api/status > /dev/null 2>&1; then
    echo "✓ Application is healthy!"
    break
  fi

  RETRY_COUNT=$((RETRY_COUNT + 1))
  echo "Waiting for application to be ready... ($RETRY_COUNT/$MAX_RETRIES)"
  sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
  echo "✗ Application health check failed!"
  echo "Showing logs:"
  docker-compose -f "${COMPOSE_FILE}" logs --tail=50 app
  exit 1
fi

# Show logs
echo "========================================="
echo "Recent logs:"
echo "========================================="
docker-compose -f "${COMPOSE_FILE}" logs --tail=20

echo "========================================="
echo "Deployment complete!"
echo "========================================="
echo "To view logs: docker-compose -f ${COMPOSE_FILE} logs -f"
echo "To stop: docker-compose -f ${COMPOSE_FILE} down"
