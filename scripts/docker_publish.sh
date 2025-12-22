#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"
DOCKER_REPO="${DOCKER_REPO:-astrogenomics/symclatron}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

if [[ -z "$VERSION" ]]; then
  echo "Usage: $(basename "$0") <version>"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required to build and push the image."
  exit 1
fi

docker buildx build \
  --platform "$PLATFORMS" \
  --build-arg "SYMCLATRON_VERSION=$VERSION" \
  -t "$DOCKER_REPO:$VERSION" \
  -t "$DOCKER_REPO:latest" \
  --push .
