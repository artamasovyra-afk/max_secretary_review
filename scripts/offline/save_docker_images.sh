#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.prod.yml"
IMAGE_DIR="$REPO_ROOT/vendor/docker-images"
RELEASE_VERSION="${RELEASE_VERSION:-1.0.0}"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 127
    fi
}

log() {
    printf '\n== %s ==\n' "$1"
}

compose_image_ref() {
    local service="$1"
    local line

    line="$(docker compose -f "$COMPOSE_FILE" images --format '{{.Service}} {{.Repository}}:{{.Tag}}' | awk -v service="$service" '$1 == service {print $2; exit}')"
    if [[ -z "$line" || "$line" == "<none>:<none>" ]]; then
        echo "Unable to determine image name for compose service: $service" >&2
        docker compose -f "$COMPOSE_FILE" images >&2
        exit 1
    fi
    printf '%s\n' "$line"
}

save_image() {
    local image_ref="$1"
    local target_file="$2"

    echo "Saving $image_ref -> $target_file"
    docker save "$image_ref" -o "$target_file"
}

if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "Missing compose file: $COMPOSE_FILE" >&2
    exit 1
fi

require_command docker

log "Build production images"
echo "Repository: $REPO_ROOT"
echo "Compose file: $COMPOSE_FILE"
echo "Docker image directory: $IMAGE_DIR"
mkdir -p "$IMAGE_DIR"

docker compose -f "$COMPOSE_FILE" build

BACKEND_IMAGE="$(compose_image_ref backend)"
WEBAPP_IMAGE="$(compose_image_ref webapp)"

log "Save images"
save_image "$BACKEND_IMAGE" "$IMAGE_DIR/max_secretary_backend_${RELEASE_VERSION}.tar"
save_image "$WEBAPP_IMAGE" "$IMAGE_DIR/max_secretary_webapp_${RELEASE_VERSION}.tar"
save_image "nginx:stable" "$IMAGE_DIR/nginx_stable.tar"
save_image "postgres:16" "$IMAGE_DIR/postgres_16.tar"
save_image "redis:7" "$IMAGE_DIR/redis_7.tar"

TAR_COUNT="$(find "$IMAGE_DIR" -maxdepth 1 -type f -name '*.tar' | wc -l | tr -d '[:space:]')"

log "Summary"
echo "docker_image_archives=$TAR_COUNT"
echo "docker_image_path=$IMAGE_DIR"
find "$IMAGE_DIR" -maxdepth 1 -type f -name '*.tar' -print | sort
