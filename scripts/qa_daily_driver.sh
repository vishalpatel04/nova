#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PASS=0
FAIL=0
API_BASE="${NOVA_API_BASE:-http://localhost:8000}"
OLLAMA_BASE="${NOVA_OLLAMA_BASE_URL:-http://localhost:11434}"

pass() { echo "  PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL  $1"; FAIL=$((FAIL + 1)); }

check_cmd() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then pass "$name"; else fail "$name"; fi
}

echo "== NOVA Daily Driver QA =="
echo "Branch: $(git branch --show-current 2>/dev/null || echo unknown)"
echo "Recent commits:"
git log -3 --oneline 2>/dev/null || true
echo

echo "-- Infrastructure --"
check_cmd "docker compose config" docker compose -f infra/docker-compose.yml config -q
check_cmd "API health" curl -fsS "$API_BASE/api/v1/health"
check_cmd "API readiness" curl -fsS "$API_BASE/api/v1/readiness"

echo "-- OpenAPI routes --"
if curl -fsS "$API_BASE/openapi.json" | python3 -c '
import json, sys
spec = json.load(sys.stdin)
paths = spec.get("paths", {})
required = ["/api/v1/chat", "/api/v1/chat/stream", "/api/v1/runtime/status"]
missing = [p for p in required if p not in paths]
sys.exit(1 if missing else 0)
'; then
  pass "openapi chat/runtime routes"
else
  fail "openapi chat/runtime routes"
fi

echo "-- Ollama --"
check_cmd "Ollama running" curl -fsS "$OLLAMA_BASE/api/tags"
if curl -fsS "$OLLAMA_BASE/api/tags" | python3 -c '
import json, sys
models = [m.get("name", "") for m in json.load(sys.stdin).get("models", [])]
sys.exit(0 if any("qwen2.5" in m for m in models) else 1)
'; then
  pass "qwen2.5 model installed"
else
  fail "qwen2.5 model installed"
fi

echo "-- Worker --"
if bash scripts/worker-launchd-status.sh >/dev/null 2>&1; then
  pass "worker launchd loaded"
else
  fail "worker launchd loaded"
fi

TOKEN=""
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
fi
if [[ -z "${TOKEN:-}" && -n "${NOVA_CLIENT_TOKEN:-}" ]]; then
  TOKEN="$NOVA_CLIENT_TOKEN"
fi
if [[ -z "${TOKEN:-}" ]]; then
  for svc in com.nova.macos com.nova.macos.genie.credentials; do
    candidate="$(security find-generic-password -s "$svc" -w 2>/dev/null | head -1 || true)"
    if [[ -n "$candidate" ]]; then
      TOKEN="$candidate"
      break
    fi
  done
fi

if [[ -n "$TOKEN" ]]; then
  echo "-- Authenticated smoke --"
  if curl -fsS -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message":"help"}' \
    "$API_BASE/api/v1/chat" | python3 -c '
import json, sys
data = json.load(sys.stdin)
sys.exit(0 if data.get("blocked") is False else 1)
'; then
    pass "authenticated chat"
  else
    fail "authenticated chat"
  fi

  if curl -fsS -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message":"read file ~/.ssh/id_rsa"}' \
    "$API_BASE/api/v1/chat" | python3 -c '
import json, sys
data = json.load(sys.stdin)
sys.exit(0 if data.get("blocked") is True else 1)
'; then
    pass "protected path block smoke"
  else
    fail "protected path block smoke"
  fi
else
  echo "-- Skipping authenticated smoke (set NOVA_CLIENT_TOKEN in env) --"
fi

echo
echo "Results: $PASS passed, $FAIL failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
