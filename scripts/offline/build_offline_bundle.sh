#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

require_command() {
    local command_name="$1"
    local error_message="$2"

    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "$error_message" >&2
        exit 127
    fi
}

log() {
    printf '\n== %s ==\n' "$1"
}

run_step() {
    local title="$1"
    local script_path="$2"

    log "$title"
    "$script_path"
}

require_command "$PYTHON_BIN" "Python is required to build offline bundle wheels."
require_command docker "Docker is required to build offline bundle images."

log "Offline bundle build"
echo "Repository: $REPO_ROOT"
echo "Python: $("$PYTHON_BIN" --version)"
echo "Docker: $(docker --version)"

run_step "Build Python wheelhouse" "$REPO_ROOT/scripts/offline/build_python_wheelhouse.sh"
run_step "Save Docker images" "$REPO_ROOT/scripts/offline/save_docker_images.sh"
run_step "Build release manifest and checksums" "$REPO_ROOT/scripts/offline/build_release_manifest.sh"

log "Summary"
echo "offline_bundle=ready"
echo "vendor_path=$REPO_ROOT/vendor"
find "$REPO_ROOT/vendor" -maxdepth 2 -type f | sort
