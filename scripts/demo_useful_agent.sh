#!/usr/bin/env bash
# Milestone 1 end-to-end demo — isolated project under ~/Desktop/NOVA-Safe-Test only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${NOVA_API_URL:-http://localhost:8000}"
ADMIN_TOKEN="${NOVA_ADMIN_TOKEN:-nova_bts_dev_bootstrap}"
SAFE_ROOT="${NOVA_SAFE_ROOT:-$HOME/Desktop/NOVA-Safe-Test}"
TOKEN="${NOVA_DEMO_TOKEN:-}"
PASS=0
DEMO_DIR=""

# Safe debug: log steps without bash -x (avoids leaking Authorization headers/tokens).
demo_debug() {
  if [[ "${NOVA_DEMO_DEBUG:-}" == "1" ]]; then
    echo "[debug] $*" >&2
  fi
}

# Print API error bodies without token fields.
sanitize_api_error() {
  local file="${1:-}"
  if [[ -z "$file" || ! -f "$file" ]]; then
    echo "  (empty response body)"
    return
  fi
  python3 - "$file" <<'PY'
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").strip()
if not raw:
    print("  (empty response body)")
    raise SystemExit(0)

def scrub(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key.lower() in {"token", "ticket", "authorization"}:
                out[key] = "***"
            else:
                out[key] = scrub(item)
        return out
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str) and value.startswith(("nova_bts_", "nova_cli_", "nova_wrk_")):
        return "***"
    return value

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    preview = raw[:400].replace("\n", " ")
    print(f"  {preview}")
    raise SystemExit(0)

clean = scrub(data)
text = json.dumps(clean, indent=2)
if len(text) > 800:
    text = text[:800] + "\n  … (truncated)"
print(text)
PY
}

api_request() {
  local method="$1"
  local path="$2"
  local auth_token="${3:-}"
  local body="${4:-}"
  local tmp http_code
  local curl_args=(-sS -w "%{http_code}" -o)

  tmp="$(mktemp "${TMPDIR:-/tmp}/nova-demo-resp.XXXXXX")"
  curl_args+=("$tmp" -X "$method" "$API$path")
  if [[ -n "$auth_token" ]]; then
    curl_args+=(-H "Authorization: Bearer $auth_token")
  fi
  if [[ -n "$body" ]]; then
    curl_args+=(-H "Content-Type: application/json" -d "$body")
  fi

  http_code="$(curl "${curl_args[@]}")"

  demo_debug "$method $path -> HTTP $http_code"

  if [[ "$http_code" -ge 400 ]]; then
    echo "FAIL: $method $path (HTTP $http_code)" >&2
    sanitize_api_error "$tmp" >&2
    rm -f "$tmp"
    return 1
  fi

  cat "$tmp"
  rm -f "$tmp"
}

obtain_client_token() {
  if [[ -n "$TOKEN" ]]; then
    demo_debug "Using NOVA_DEMO_TOKEN from environment"
    return 0
  fi

  local device_id="demo-client-$$"
  local create pairing_id code claim tmp

  tmp="$(mktemp "${TMPDIR:-/tmp}/nova-demo-resp.XXXXXX")"
  if ! http_code="$(curl -sS -w "%{http_code}" -o "$tmp" -X POST "$API/api/v1/pairing/codes" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"device_type\":\"iphone_client\",\"proposed_device_id\":\"$device_id\"}")"; then
    rm -f "$tmp"
    echo "WARN: could not reach pairing API (set NOVA_ADMIN_TOKEN / NOVA_DEMO_TOKEN)"
    return 1
  fi
  if [[ "$http_code" -ge 400 ]]; then
    echo "WARN: pairing code creation failed (HTTP $http_code)"
    sanitize_api_error "$tmp"
    rm -f "$tmp"
    echo "Set NOVA_ADMIN_TOKEN to your bootstrap admin value or NOVA_DEMO_TOKEN to a paired client token."
    return 1
  fi
  create="$(cat "$tmp")"
  rm -f "$tmp"

  code="$(echo "$create" | python3 -c "import sys,json; print(json.load(sys.stdin)['code'])")"
  pairing_id="$(echo "$create" | python3 -c "import sys,json; print(json.load(sys.stdin)['pairing_id'])")"

  claim="$(api_request POST "/api/v1/pairing/claim" "" \
    "{\"code\":\"$code\",\"device_id\":\"$device_id\",\"name\":\"Demo Client\",\"device_type\":\"iphone_client\"}")" || return 1

  if echo "$claim" | grep -q '"status":"pending"'; then
    api_request POST "/api/v1/pairing/$pairing_id/approve" "$ADMIN_TOKEN" >/dev/null
    tmp="$(mktemp "${TMPDIR:-/tmp}/nova-demo-resp.XXXXXX")"
    http_code="$(curl -sS -w "%{http_code}" -o "$tmp" -X POST "$API/api/v1/pairing/$pairing_id/token" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"device_id\":\"$device_id\"}")"
    if [[ "$http_code" -ge 400 ]]; then
      echo "WARN: could not retrieve pairing token (HTTP $http_code)"
      sanitize_api_error "$tmp"
      rm -f "$tmp"
      return 1
    fi
    TOKEN="$(python3 -c "import sys,json; print(json.load(open(sys.argv[1]))['token'])" "$tmp")"
    rm -f "$tmp"
  else
    TOKEN="$(echo "$claim" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")"
  fi

  demo_debug "Obtained ephemeral demo client token (not printed)"
  return 0
}

cleanup() {
  demo_restore_active_project
  if [[ -n "$DEMO_DIR" && -d "$DEMO_DIR" ]]; then
    case "$DEMO_DIR" in
      "$SAFE_ROOT"/milestone-demo-*)
        rm -rf "$DEMO_DIR"
        demo_debug "Removed demo directory $DEMO_DIR"
        ;;
      *)
        echo "WARN: skip cleanup — demo dir outside safe root: $DEMO_DIR" >&2
        ;;
    esac
  fi
}
trap cleanup EXIT

echo "== NOVA Milestone 1 Demo =="

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

# shellcheck source=demo_project_helpers.sh
source "$ROOT/scripts/demo_project_helpers.sh"
demo_save_active_project

curl -sf "$API/api/v1/system/status" -H "Authorization: Bearer $ADMIN_TOKEN" | head -c 200 || true
echo

step "5. Create isolated demo project under allowlisted safe root"
mkdir -p "$SAFE_ROOT"
DEMO_DIR="$(mktemp -d "$SAFE_ROOT/milestone-demo-XXXXXX")"
echo "Demo project: $DEMO_DIR"

mkdir -p "$DEMO_DIR/tests"
cat >"$DEMO_DIR/Makefile" <<'EOF'
.PHONY: test
test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v
EOF
cat >"$DEMO_DIR/tests/test_demo.py" <<'EOF'
import unittest


class DemoTest(unittest.TestCase):
    def test_demo(self):
        assert False
EOF
(
  cd "$DEMO_DIR"
  git init -q
  git -c user.email=demo@nova.local -c user.name="NOVA Demo" add Makefile tests/test_demo.py
  git -c user.email=demo@nova.local -c user.name="NOVA Demo" commit -q -m "demo fixture"
)

PROJECT_PATH="$DEMO_DIR"

step "6. Set active project"
SET_PROJECT="$(api_request POST "/api/v1/projects/active" "$TOKEN" \
  "{\"project_root\":\"$PROJECT_PATH\"}")"
echo "$SET_PROJECT" | head -c 300
echo

step "7. Inspect repo"
INSPECT="$(api_request POST "/api/v1/projects/inspect" "$TOKEN")"
echo "$INSPECT" | head -c 400
echo

step "8. Run validation (expect failure)"
VAL="$(api_request POST "/api/v1/projects/validate" "$TOKEN")"
echo "$VAL" | head -c 400
echo

step "9. Ask NOVA to propose patch via coding task"
CHAT="$(api_request POST "/api/v1/chat" "$TOKEN" '{"message":"fix failing tests"}')"
echo "$CHAT" | head -c 500
echo
APPROVAL_ID="$(echo "$CHAT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('approval_id') or '')" 2>/dev/null || true)"
if [[ -z "$APPROVAL_ID" ]]; then
  APPROVAL_ID="$(echo "$CHAT" | grep -oE '[0-9a-f-]{36}' | head -1 || true)"
fi

if [[ -n "$APPROVAL_ID" ]]; then
  step "10. Approve patch"
  api_request POST "/api/v1/approvals/$APPROVAL_ID/approve" "$TOKEN" >/dev/null
  echo "OK: approved"

  step "11. Apply approved patch"
  APPLY="$(api_request POST "/api/v1/executions/apply-approved-patch" "$TOKEN" \
    "{\"approval_id\":\"$APPROVAL_ID\"}")"
  echo "$APPLY" | head -c 400
  echo

  step "12. Rerun validation"
  VAL2="$(api_request POST "/api/v1/projects/validate" "$TOKEN")"
  EXIT="$(echo "$VAL2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('exit_code',1))")"
  echo "exit_code=$EXIT"
  if [[ "$EXIT" == "0" ]]; then
    echo "PASS: validation succeeded after patch"
    PASS=1
  else
    echo "FAIL: validation still failing"
  fi

  step "13. Replay approval (expect blocked)"
  tmp="$(mktemp "${TMPDIR:-/tmp}/nova-demo-resp.XXXXXX")"
  REPLAY="$(curl -sS -w "%{http_code}" -o "$tmp" -X POST "$API/api/v1/executions/apply-approved-patch" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"approval_id\":\"$APPROVAL_ID\"}")"
  echo "replay HTTP $REPLAY (expect 409)"
  if [[ "$REPLAY" -ge 400 ]]; then
    sanitize_api_error "$tmp" | head -c 200
    echo
  fi
  rm -f "$tmp"
else
  echo "WARN: no approval_id from chat — demo partial"
fi

echo
if [[ "$PASS" == "1" ]]; then
  echo "DEMO: PASS"
  exit 0
fi
echo "DEMO: PARTIAL"
exit 0
