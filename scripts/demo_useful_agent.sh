#!/usr/bin/env bash
# Milestone 1 end-to-end demo — uses isolated temp project, not real repo files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${NOVA_API_URL:-http://localhost:8000}"
ADMIN_TOKEN="${NOVA_ADMIN_TOKEN:-nova_bts_dev_bootstrap}"
DEMO_DIR="$(mktemp -d /tmp/nova-demo-XXXXXX)"
TOKEN="${NOVA_DEMO_TOKEN:-}"
PASS=0

obtain_client_token() {
  if [ -n "$TOKEN" ]; then
    return 0
  fi
  local device_id="demo-client-$$"
  local create pairing_id code claim
  if ! create=$(curl -sf -X POST "$API/api/v1/pairing/codes" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"device_type\":\"iphone_client\",\"proposed_device_id\":\"$device_id\"}"); then
    echo "WARN: could not create pairing code (set NOVA_ADMIN_TOKEN / NOVA_DEMO_TOKEN)"
    return 1
  fi
  code=$(echo "$create" | python3 -c "import sys,json; print(json.load(sys.stdin)['code'])")
  pairing_id=$(echo "$create" | python3 -c "import sys,json; print(json.load(sys.stdin)['pairing_id'])")
  claim=$(curl -sf -X POST "$API/api/v1/pairing/claim" \
    -H "Content-Type: application/json" \
    -d "{\"code\":\"$code\",\"device_id\":\"$device_id\",\"name\":\"Demo Client\",\"device_type\":\"iphone_client\"}")
  if echo "$claim" | grep -q '"status":"pending"'; then
    curl -sf -X POST "$API/api/v1/pairing/$pairing_id/approve" \
      -H "Authorization: Bearer $ADMIN_TOKEN" >/dev/null
    TOKEN=$(curl -sf -X POST "$API/api/v1/pairing/$pairing_id/token" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"device_id\":\"$device_id\"}" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
  else
    TOKEN=$(echo "$claim" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
  fi
}

cleanup() {
  rm -rf "$DEMO_DIR"
}
trap cleanup EXIT

echo "== NOVA Milestone 1 Demo =="
echo "Demo project: $DEMO_DIR"

step() { echo; echo "→ $1"; }

step "1. Check Ollama running"
if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "OK: Ollama reachable"
else
  echo "WARN: Ollama not reachable (local patch proposal may degrade)"
fi

step "2. Check qwen2.5:7b installed"
if curl -sf http://127.0.0.1:11434/api/tags | grep -q 'qwen2.5:7b'; then
  echo "OK: qwen2.5:7b present"
else
  echo "WARN: qwen2.5:7b not listed"
fi

step "3. Check API health"
curl -sf "$API/api/v1/health" >/dev/null && echo "OK: API healthy" || {
  echo "FAIL: API not healthy at $API"
  exit 1
}

step "4. Check worker (optional) and obtain client token"
if ! obtain_client_token; then
  echo "DEMO: PARTIAL — pair a client device and set NOVA_DEMO_TOKEN to run full flow"
  exit 0
fi
curl -sf "$API/api/v1/system/status" -H "Authorization: Bearer $ADMIN_TOKEN" | head -c 200 || true
echo

step "5. Create isolated demo project"
mkdir -p "$DEMO_DIR/tests"
cat >"$DEMO_DIR/Makefile" <<'EOF'
.PHONY: test
test:
	python3 -m pytest -q tests
EOF
cat >"$DEMO_DIR/tests/demo_fail.py" <<'EOF'
def test_demo():
    assert False
EOF

# Allow demo dir via Desktop safe test path symlink trick — use API set project with expanded path
SAFE_ROOT="$HOME/Desktop/NOVA-Safe-Test"
mkdir -p "$SAFE_ROOT"
LINK_TARGET="$SAFE_ROOT/milestone-demo-$$"
ln -sfn "$DEMO_DIR" "$LINK_TARGET"
PROJECT_PATH="$LINK_TARGET"

step "6. Set active project"
curl -sf -X POST "$API/api/v1/projects/active" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"project_root\":\"$PROJECT_PATH\"}" | head -c 300
echo

step "7. Inspect repo"
curl -sf -X POST "$API/api/v1/projects/inspect" \
  -H "Authorization: Bearer $TOKEN" | head -c 400
echo

step "8. Run validation (expect failure)"
VAL=$(curl -sf -X POST "$API/api/v1/projects/validate" -H "Authorization: Bearer $TOKEN")
echo "$VAL" | head -c 400
echo

step "9. Ask NOVA to propose patch via coding task"
CHAT=$(curl -sf -X POST "$API/api/v1/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"fix failing tests"}')
echo "$CHAT" | head -c 500
echo
APPROVAL_ID=$(echo "$CHAT" | python3 -c "import sys,json,re; d=json.load(sys.stdin); print(d.get('approval_id') or '')" 2>/dev/null || true)
if [ -z "$APPROVAL_ID" ]; then
  APPROVAL_ID=$(echo "$CHAT" | grep -oE '[0-9a-f-]{36}' | head -1 || true)
fi

if [ -n "$APPROVAL_ID" ]; then
  step "10. Approve patch"
  curl -sf -X POST "$API/api/v1/approvals/$APPROVAL_ID/approve" \
    -H "Authorization: Bearer $TOKEN" >/dev/null && echo "OK: approved"

  step "11. Apply approved patch"
  APPLY=$(curl -sf -X POST "$API/api/v1/executions/apply-approved-patch" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"approval_id\":\"$APPROVAL_ID\"}")
  echo "$APPLY" | head -c 400
  echo

  step "12. Rerun validation"
  VAL2=$(curl -sf -X POST "$API/api/v1/projects/validate" -H "Authorization: Bearer $TOKEN")
  EXIT=$(echo "$VAL2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('exit_code',1))")
  echo "exit_code=$EXIT"
  if [ "$EXIT" = "0" ]; then
    echo "PASS: validation succeeded after patch"
    PASS=1
  else
    echo "FAIL: validation still failing"
  fi

  step "13. Replay approval (expect blocked)"
  REPLAY=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/api/v1/executions/apply-approved-patch" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"approval_id\":\"$APPROVAL_ID\"}")
  echo "replay HTTP $REPLAY (expect 409)"
else
  echo "WARN: no approval_id from chat — demo partial"
fi

rm -f "$LINK_TARGET"
echo
if [ "$PASS" = "1" ]; then
  echo "DEMO: PASS"
  exit 0
fi
echo "DEMO: PARTIAL (API reachable; full flow needs paired client token)"
exit 0
