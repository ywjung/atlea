#!/bin/bash
set -e

# Docker build script with optimization
# Usage: ./docker-build.sh [tag]

TAG="${1:-latest}"
IMAGE_NAME="chatbot-app"
REGISTRY="${DOCKER_REGISTRY:-}"

echo "========================================="
echo "Building Docker Image"
echo "========================================="
echo "Image: ${IMAGE_NAME}:${TAG}"
echo "Registry: ${REGISTRY:-local}"
echo "========================================="

# Enable BuildKit for better caching and performance
export DOCKER_BUILDKIT=1

# Build the image
echo "Building image..."
docker build \
  --tag "${IMAGE_NAME}:${TAG}" \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  --progress=plain \
  .

# Tag with latest
if [ "$TAG" != "latest" ]; then
  echo "Tagging as latest..."
  docker tag "${IMAGE_NAME}:${TAG}" "${IMAGE_NAME}:latest"
fi

# Show image details
echo "========================================="
echo "Image built successfully!"
echo "========================================="
docker images | grep "${IMAGE_NAME}"

# Show image size
IMAGE_SIZE=$(docker images "${IMAGE_NAME}:${TAG}" --format "{{.Size}}")
echo "Image size: ${IMAGE_SIZE}"

# Push to registry if specified
if [ -n "${REGISTRY}" ]; then
  echo "========================================="
  echo "Pushing to registry: ${REGISTRY}"
  echo "========================================="

  docker tag "${IMAGE_NAME}:${TAG}" "${REGISTRY}/${IMAGE_NAME}:${TAG}"
  docker push "${REGISTRY}/${IMAGE_NAME}:${TAG}"

  if [ "$TAG" != "latest" ]; then
    docker tag "${IMAGE_NAME}:${TAG}" "${REGISTRY}/${IMAGE_NAME}:latest"
    docker push "${REGISTRY}/${IMAGE_NAME}:latest"
  fi

  echo "Image pushed successfully!"
fi

# Optional: Run security scan
if command -v trivy &> /dev/null; then
  echo "========================================="
  echo "Running security scan..."
  echo "========================================="
  trivy image --severity HIGH,CRITICAL "${IMAGE_NAME}:${TAG}"
fi

echo "========================================="
echo "Build complete!"
echo "========================================="
