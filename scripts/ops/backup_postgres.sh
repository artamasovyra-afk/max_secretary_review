#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/max_secretary_${TIMESTAMP}.sql.gz"

log() {
    printf '\n== %s ==\n' "$1"
}

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required to create PostgreSQL backup." >&2
    exit 127
fi

cd "$REPO_ROOT"
mkdir -p "$BACKUP_DIR"

log "Create PostgreSQL backup"
echo "Compose file: $COMPOSE_FILE"
echo "Backup file: $BACKUP_FILE"

docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c \
    'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    | gzip -c > "$BACKUP_FILE"

log "Summary"
echo "backup_file=$BACKUP_FILE"
ls -lh "$BACKUP_FILE"
