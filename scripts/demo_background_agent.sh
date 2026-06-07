#!/usr/bin/env bash
# Milestone 2 background agent demo — isolated project under ~/Desktop/NOVA-Safe-Test only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${NOVA_API_URL:-http://localhost:8000}"
ADMIN_TOKEN="${NOVA_ADMIN_TOKEN:-nova_bts_dev_bootstrap}"
SAFE_ROOT="${NOVA_SAFE_ROOT:-$HOME/Desktop/NOVA-Safe-Test}"
TOKEN="${NOVA_DEMO_TOKEN:-}"
PASS=0
DEMO_DIR=""
TASK_ID=""

demo_debug() {
  if [[ "${NOVA_DEMO_DEBUG:-}" == "1" ]]; then
    echo "[debug] $*" >&2
  fi
}

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

  local device_id="demo-bg-client-$$"
  local create pairing_id code claim tmp http_code

  tmp="$(mktemp "${TMPDIR:-/tmp}/nova-demo-resp.XXXXXX")"
  http_code="$(curl -sS -w "%{http_code}" -o "$tmp" -X POST "$API/api/v1/pairing/codes" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"device_type\":\"iphone_client\",\"proposed_device_id\":\"$device_id\"}")"
  if [[ "$http_code" -ge 400 ]]; then
    sanitize_api_error "$tmp"
    rm -f "$tmp"
    return 1
  fi
  create="$(cat "$tmp")"
  rm -f "$tmp"

  code="$(echo "$create" | python3 -c "import sys,json; print(json.load(sys.stdin)['code'])")"
  pairing_id="$(echo "$create" | python3 -c "import sys,json; print(json.load(sys.stdin)['pairing_id'])")"

  claim="$(api_request POST "/api/v1/pairing/claim" "" \
    "{\"code\":\"$code\",\"device_id\":\"$device_id\",\"name\":\"Demo BG Client\",\"device_type\":\"iphone_client\"}")" || return 1

  if echo "$claim" | grep -q '"status":"pending"'; then
    api_request POST "/api/v1/pairing/$pairing_id/approve" "$ADMIN_TOKEN" >/dev/null
    tmp="$(mktemp "${TMPDIR:-/tmp}/nova-demo-resp.XXXXXX")"
    http_code="$(curl -sS -w "%{http_code}" -o "$tmp" -X POST "$API/api/v1/pairing/$pairing_id/token" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"device_id\":\"$device_id\"}")"
    if [[ "$http_code" -ge 400 ]]; then
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
  if [[ -n "$DEMO_DIR" && -d "$DEMO_DIR" ]]; then
    case "$DEMO_DIR" in
      "$SAFE_ROOT"/bg-demo-*)
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

step() { echo; echo "→ $1"; }

echo "== NOVA Milestone 2 Background Agent Demo =="

step "1. Verify Ollama"
if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "OK: Ollama reachable"
else
  echo "WARN: Ollama not reachable"
fi

step "2. Verify API"
curl -sf "$API/api/v1/health" >/dev/null && echo "OK: API healthy" || {
  echo "FAIL: API not healthy"
  exit 1
}

step "3. Verify worker (optional)"
curl -sf "$API/api/v1/system/status" -H "Authorization: Bearer $ADMIN_TOKEN" | head -c 200 || true
echo

step "4. Obtain paired client token"
if ! obtain_client_token; then
  echo "DEMO: PARTIAL — set NOVA_DEMO_TOKEN"
  exit 0
fi

step "5. Create isolated safe project"
mkdir -p "$SAFE_ROOT"
DEMO_DIR="$(mktemp -d "$SAFE_ROOT/bg-demo-XXXXXX")"
mkdir -p "$DEMO_DIR/tests"
cat >"$DEMO_DIR/Makefile" <<'EOF'
.PHONY: test
test:
	python3 -m unittest discover -s tests -p 'test_*.py' -q
EOF
cat >"$DEMO_DIR/tests/test_demo.py" <<'EOF'
import unittest

class DemoTest(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
EOF
(
  cd "$DEMO_DIR"
  git init -q
  git -c user.email=demo@nova.local -c user.name="NOVA Demo" add Makefile tests/test_demo.py
  git -c user.email=demo@nova.local -c user.name="NOVA Demo" commit -q -m "bg demo fixture"
)
PROJECT_PATH="$DEMO_DIR"
echo "Demo project: $PROJECT_PATH"

step "6. Create repo validation background task"
api_request POST "/api/v1/projects/active" "$TOKEN" "{\"project_root\":\"$PROJECT_PATH\"}" >/dev/null
CREATE="$(api_request POST "/api/v1/background-tasks" "$TOKEN" \
  "{\"task_type\":\"repo.run_validation\",\"title\":\"BG validation demo\",\"project_root\":\"$PROJECT_PATH\",\"schedule_kind\":\"interval\",\"schedule_expression\":\"6h\"}")"
TASK_ID="$(echo "$CREATE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")"
echo "Task id: $TASK_ID"

step "7. Run task now"
RUN1="$(api_request POST "/api/v1/background-tasks/$TASK_ID/run-now" "$TOKEN")"
echo "$RUN1" | head -c 400
echo
STATUS1="$(echo "$RUN1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")"
[[ "$STATUS1" == "succeeded" ]] || { echo "FAIL: expected initial success"; exit 1; }

step "8. Initial success confirmed"
echo "OK"

step "9. Introduce isolated failing fixture"
cat >"$DEMO_DIR/tests/test_demo.py" <<'EOF'
import unittest

class DemoTest(unittest.TestCase):
    def test_fail(self):
        self.assertTrue(False)
EOF

step "10. Run task now (expect failure)"
RUN2="$(api_request POST "/api/v1/background-tasks/$TASK_ID/run-now" "$TOKEN")"
STATUS2="$(echo "$RUN2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")"
echo "status=$STATUS2"
[[ "$STATUS2" == "failed" ]] || { echo "FAIL: expected validation failure"; exit 1; }

step "11. Confirm failure notification"
NOTES="$(api_request GET "/api/v1/notifications" "$TOKEN")"
echo "$NOTES" | head -c 400
echo
echo "$NOTES" | grep -q 'validation.failed' && echo "OK: failure notification" || {
  echo "FAIL: missing validation.failed notification"
  exit 1
}

step "12. Fix fixture manually"
cat >"$DEMO_DIR/tests/test_demo.py" <<'EOF'
import unittest

class DemoTest(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
EOF

step "13. Run task now (expect recovery)"
RUN3="$(api_request POST "/api/v1/background-tasks/$TASK_ID/run-now" "$TOKEN")"
STATUS3="$(echo "$RUN3" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")"
echo "status=$STATUS3"
[[ "$STATUS3" == "succeeded" ]] || { echo "FAIL: expected recovery success"; exit 1; }

step "14. Confirm recovery notification"
NOTES2="$(api_request GET "/api/v1/notifications" "$TOKEN")"
echo "$NOTES2" | grep -q 'validation.recovered' && echo "OK: recovery notification" || {
  echo "FAIL: missing validation.recovered notification"
  exit 1
}

step "15. Pause task"
api_request POST "/api/v1/background-tasks/$TASK_ID/pause" "$TOKEN" >/dev/null
echo "OK: paused"

step "16. Verify paused task does not run"
tmp="$(mktemp "${TMPDIR:-/tmp}/nova-demo-resp.XXXXXX")"
HTTP="$(curl -sS -w "%{http_code}" -o "$tmp" -X POST "$API/api/v1/background-tasks/$TASK_ID/run-now" \
  -H "Authorization: Bearer $TOKEN")"
echo "run-now while paused: HTTP $HTTP (expect 409)"
[[ "$HTTP" == "409" ]] || { echo "FAIL: paused task should block run-now"; exit 1; }
rm -f "$tmp"

step "17. Resume task"
api_request POST "/api/v1/background-tasks/$TASK_ID/resume" "$TOKEN" >/dev/null
echo "OK: resumed"

step "18. Cancel task"
api_request POST "/api/v1/background-tasks/$TASK_ID/cancel" "$TOKEN" >/dev/null
echo "OK: cancelled"

step "19. Verify cross-device protection"
tmp="$(mktemp "${TMPDIR:-/tmp}/nova-demo-resp.XXXXXX")"
HTTP="$(curl -sS -w "%{http_code}" -o "$tmp" -X GET "$API/api/v1/background-tasks/$TASK_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN")"
echo "admin cross-read: HTTP $HTTP (expect 401/403/404)"
[[ "$HTTP" -ge 400 ]] || { echo "FAIL: cross-device/admin read should be blocked"; exit 1; }
rm -f "$tmp"

step "20. Clean up isolated project"
rm -rf "$DEMO_DIR"
DEMO_DIR=""
echo "OK: cleaned"

step "21. Final result"
PASS=1
echo
echo "DEMO: PASS"
exit 0
