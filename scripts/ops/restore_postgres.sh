#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_FILE="${1:-}"

log() {
    printf '\n== %s ==\n' "$1"
}

if [[ -z "$BACKUP_FILE" ]]; then
    echo "Usage: scripts/ops/restore_postgres.sh <backup-file.sql.gz>" >&2
    exit 2
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "Backup file not found: $BACKUP_FILE" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required to restore PostgreSQL backup." >&2
    exit 127
fi

cat >&2 <<'WARNING'
WARNING: PostgreSQL restore will overwrite data in the target database.
Make sure you have a fresh backup before continuing.
WARNING

read -r -p "Type RESTORE to continue: " CONFIRMATION
if [[ "$CONFIRMATION" != "RESTORE" ]]; then
    echo "Restore cancelled." >&2
    exit 1
fi

cd "$REPO_ROOT"

log "Restore PostgreSQL backup"
echo "Compose file: $COMPOSE_FILE"
echo "Backup file: $BACKUP_FILE"

gunzip -c "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c \
    'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'

log "Summary"
echo "restore=completed"
