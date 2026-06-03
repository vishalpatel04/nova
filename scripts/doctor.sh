#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PASS=0
FAIL=0

check() {
    local name="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  ✓ $name"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $name"
        FAIL=$((FAIL + 1))
    fi
}

echo "==> NOVA Doctor"
echo ""

echo "Prerequisites:"
check "Python 3.12+" python3 -c 'import sys; assert sys.version_info >= (3, 12)'
check "Docker" docker info
check "Docker Compose" docker compose version

echo ""
echo "Project:"
check "Virtual env" test -d .venv
check ".env file" test -f .env
check "Config: agents.yaml" test -f config/agents.yaml
check "Config: models.yaml" test -f config/models.yaml
check "Config: voices.yaml" test -f config/voices.yaml
check "Config: devices.yaml" test -f config/devices.yaml
check "Config: policies.yaml" test -f config/policies.yaml

echo ""
echo "Infrastructure:"
check "PostgreSQL running" docker compose -f infra/docker-compose.yml exec -T postgres pg_isready -U nova -d nova
check "Redis running" docker compose -f infra/docker-compose.yml exec -T redis redis-cli ping

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
