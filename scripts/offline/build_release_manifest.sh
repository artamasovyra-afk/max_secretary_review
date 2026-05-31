#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHECKSUM_DIR="$REPO_ROOT/vendor/checksums"
RELEASE_DIR="$REPO_ROOT/vendor/release"
MANIFEST_FILE="$RELEASE_DIR/manifest.txt"
CHECKSUM_FILE="$CHECKSUM_DIR/SHA256SUMS"

log() {
    printf '\n== %s ==\n' "$1"
}

sha256_command() {
    if command -v sha256sum >/dev/null 2>&1; then
        echo "sha256sum"
        return
    fi
    if command -v shasum >/dev/null 2>&1; then
        echo "shasum -a 256"
        return
    fi
    echo "Neither sha256sum nor shasum is available." >&2
    exit 127
}

collect_files() {
    (
        cd "$REPO_ROOT"
        find vendor/docker-images -maxdepth 1 -type f -name '*.tar' 2>/dev/null
        find vendor/python-wheels -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null
        printf '%s\n' \
            "docker-compose.offline.yml" \
            ".env.example" \
            "VERSION" \
            "CHANGELOG.md"
    ) | sort -u
}

mkdir -p "$CHECKSUM_DIR" "$RELEASE_DIR"

log "Collect offline bundle files"
mapfile -t FILES < <(collect_files)

if [[ "${#FILES[@]}" -eq 0 ]]; then
    echo "No files found for offline release manifest." >&2
    exit 1
fi

log "Write manifest"
{
    echo "max_secretary offline release manifest"
    echo "generated_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "version=$(cat "$REPO_ROOT/VERSION")"
    echo
    printf '%s\n' "${FILES[@]}"
} > "$MANIFEST_FILE"

log "Write checksums"
HASH_CMD="$(sha256_command)"
(
    cd "$REPO_ROOT"
    : > "$CHECKSUM_FILE"
    for file_path in "${FILES[@]}"; do
        if [[ ! -f "$file_path" ]]; then
            echo "Skipping missing file: $file_path" >&2
            continue
        fi
        # shellcheck disable=SC2086
        $HASH_CMD "$file_path" >> "$CHECKSUM_FILE"
    done
)

CHECKSUM_COUNT="$(wc -l < "$CHECKSUM_FILE" | tr -d '[:space:]')"

log "Summary"
echo "manifest=$MANIFEST_FILE"
echo "checksums=$CHECKSUM_FILE"
echo "checksum_entries=$CHECKSUM_COUNT"
