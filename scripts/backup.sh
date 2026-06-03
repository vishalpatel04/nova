#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$ROOT/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

docker compose -f "$ROOT/infra/docker-compose.yml" exec -T postgres \
    pg_dump -U nova nova > "$BACKUP_DIR/nova_${TIMESTAMP}.sql"

echo "Backup saved to $BACKUP_DIR/nova_${TIMESTAMP}.sql"
