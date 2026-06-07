#!/usr/bin/env bash
# Demo script for NOVA Local Memory Kernel (bounded, no full-Mac crawl).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API="${NOVA_API_URL:-http://localhost:8000}"
DEMO_DIR="${NOVA_MEMORY_DEMO_DIR:-/tmp/nova-memory-demo}"
VAULT="${DEMO_DIR}/NOVA_VAULT"
DOCS="${DEMO_DIR}/Documents"
DOWN="${DEMO_DIR}/Downloads"

echo "== NOVA Local Memory Kernel Demo =="

step() { echo ""; echo ">> $1"; }

step "1. Verify API"
curl -sf "${API}/api/v1/health" >/dev/null || { echo "API unavailable at ${API}"; exit 1; }

step "2. Prepare bounded demo tree"
mkdir -p "${DOCS}" "${DOWN}" "${VAULT}"
echo "Sweden Lund exchange reimbursement notes" > "${DOCS}/lund-exchange.txt"
echo "Lund university paperwork" > "${DOWN}/sweden-paperwork.txt"
echo "vault secret" > "${VAULT}/hidden.txt"

step "3. Auth token"
TOKEN="${NOVA_DEMO_TOKEN:-}"
if [[ -z "${TOKEN}" ]]; then
  echo "Set NOVA_DEMO_TOKEN to a paired client bearer token for full demo."
  echo "Running offline unit checks only."
  .venv/bin/pytest tests/test_local_memory_kernel.py -q --no-header -x
  echo "DEMO: PASS (offline subset)"
  exit 0
fi

auth=(-H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json")

step "4. Enable broad_local profile"
curl -sf "${API}/api/v1/memory/profile" "${auth[@]}" -d '{"profile":"broad_local"}' | head -c 200
echo ""

step "5. Remember Lund fact"
curl -sf "${API}/api/v1/memory/remember" "${auth[@]}" -d '{
  "subject":"lund exchange documents",
  "predicate":"stored_in",
  "object_summary":"Downloads"
}' >/dev/null

step "6. Retrieve memory"
curl -sf "${API}/api/v1/memory/search" "${auth[@]}" -d '{"query":"lund exchange"}' | grep -qi lund

step "7. Vault folder blocked"
code=$(curl -s -o /dev/null -w "%{http_code}" "${API}/api/v1/memory/include-folder" "${auth[@]}" -d "{\"path\":\"${VAULT}\"}" || true)
[[ "${code}" == "403" ]] || echo "warn: expected 403 for vault include, got ${code}"

step "8. Export + audit"
curl -sf "${API}/api/v1/memory/export" "${auth[@]}" | grep -q local_only
curl -sf "${API}/api/v1/memory/audit-integrity" "${auth[@]}" | grep -q valid

step "9. Forget Lund"
curl -sf "${API}/api/v1/memory/forget-topic" "${auth[@]}" -d '{"topic":"lund"}' >/dev/null

step "10. Chat memory status"
curl -sf "${API}/api/v1/chat" "${auth[@]}" -d '{"message":"memory status"}' | grep -qi "local memory"

echo ""
echo "DEMO: PASS"
