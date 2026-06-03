#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

docker compose -f infra/docker-compose.yml down
echo "NOVA infrastructure stopped"
