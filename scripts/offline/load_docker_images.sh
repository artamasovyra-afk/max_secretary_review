#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_DIR="$REPO_ROOT/vendor/docker-images"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 127
    fi
}

log() {
    printf '\n== %s ==\n' "$1"
}

require_command docker

if [[ ! -d "$IMAGE_DIR" ]]; then
    echo "Missing Docker image directory: $IMAGE_DIR" >&2
    exit 1
fi

mapfile -t IMAGE_ARCHIVES < <(find "$IMAGE_DIR" -maxdepth 1 -type f -name '*.tar' | sort)

if [[ "${#IMAGE_ARCHIVES[@]}" -eq 0 ]]; then
    echo "No Docker image archives found in $IMAGE_DIR" >&2
    exit 1
fi

log "Load Docker images"
for image_archive in "${IMAGE_ARCHIVES[@]}"; do
    echo "Loading $image_archive"
    docker load -i "$image_archive"
done

log "Loaded images"
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}'
