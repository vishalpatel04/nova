#!/usr/bin/env bash
# Demo: full-local Archive search routing and memory status semantics.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API="${NOVA_API_URL:-http://localhost:8000}"
TOKEN="${NOVA_DEMO_TOKEN:-}"

echo "== NOVA Full-Local Search Routing Demo =="

if [[ -z "$TOKEN" ]]; then
  echo "NOVA_DEMO_TOKEN not set — running offline pytest subset"
  .venv/bin/pytest tests/test_agent_os.py::test_memory_status_routing \
    tests/test_agent_os.py::test_system_memory_status_routing \
    tests/test_agent_os.py::test_archive_search_query_parsing \
    tests/test_agent_os.py::test_chat_archive_search_intent \
    tests/test_agent_os.py::test_chat_memory_status_not_ram -q
  echo "DEMO: PASS"
  exit 0
fi

AUTH=(-H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json")

curl -sf "${API}/api/v1/memory/profile" "${AUTH[@]}" -d '{"profile":"full_local"}' >/dev/null

DEMO_DIR="${NOVA_MEMORY_DEMO_DIR:-/tmp/nova-full-local-demo}"
mkdir -p "$DEMO_DIR/Documents"
echo "Lund investor demo reimbursement notes" > "$DEMO_DIR/Documents/lund-investor-demo.txt"

curl -sf "${API}/api/v1/chat" "${AUTH[@]}" -d '{"message":"can you find Lund in my pc"}' | tee /tmp/nova-full-local-search.json
RESP=$(cat /tmp/nova-full-local-search.json)

echo "$RESP" | grep -qi "archive\|found\|lund"
echo "$RESP" | grep -qi "file explorer" && exit 1 || true
echo "$RESP" | grep -qi "win + e" && exit 1 || true
echo "$RESP" | grep -qi "don't have direct access" && exit 1 || true

curl -sf "${API}/api/v1/chat" "${AUTH[@]}" -d '{"message":"memory status"}' | tee /tmp/nova-memory-status.json
MEM=$(cat /tmp/nova-memory-status.json)
echo "$MEM" | grep -qi "NOVA memory status\|documents"
echo "$MEM" | grep -qi "vm_stat" && exit 1 || true

echo "DEMO: PASS"
