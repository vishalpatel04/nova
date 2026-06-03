#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> NOVA Bootstrap"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
fi

echo "==> Starting infrastructure"
docker compose -f infra/docker-compose.yml up -d

echo "==> Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    if docker compose -f infra/docker-compose.yml exec -T postgres pg_isready -U nova -d nova >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo "==> Running migrations"
.venv/bin/alembic upgrade head

echo "==> Bootstrap complete"
echo "Run 'make dev' to start the API"
echo "Run 'make worker' to start the worker daemon"
