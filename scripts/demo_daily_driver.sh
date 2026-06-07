#!/usr/bin/env bash
# Daily-driver demo — strict paired-client mode only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${NOVA_API_URL:-http://localhost:8000}"
SAFE_ROOT="${NOVA_SAFE_ROOT:-$HOME/Desktop/NOVA-Safe-Test}"
TOKEN="${NOVA_DEMO_TOKEN:-}"
DEMO_DIR=""
PREV_ACTIVE_PROJECT=""
CHAT_SESSION_ID=""
PASS=0

if [[ -z "$TOKEN" ]]; then
  echo "FAIL: set NOVA_DEMO_TOKEN to a paired client token" >&2
  exit 1
fi

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
  local body="${3:-}"
  local auth="${4:-$TOKEN}"
  local tmp http_code curl_args
  tmp="$(mktemp "${TMPDIR:-/tmp}/nova-daily.XXXXXX")"
  curl_args=(-sS --connect-timeout 3 --max-time 20 -w "%{http_code}" -o "$tmp" -X "$method")
  if [[ -n "$auth" ]]; then
    curl_args+=(-H "Authorization: Bearer $auth")
  fi
  if [[ -n "$body" ]]; then
    curl_args+=(-H "Content-Type: application/json" -d "$body")
  fi
  http_code="$(curl "${curl_args[@]}" "$API$path")"
  demo_debug "$method $path -> HTTP $http_code"
  if [[ "$http_code" -ge 400 ]]; then
    echo "FAIL: $method $path (HTTP $http_code)" >&2
    sanitize_api_error "$tmp" >&2
    rm -f "$tmp"
    exit 1
  fi
  cat "$tmp"
  rm -f "$tmp"
}

fetch_current_active_project() {
  local tmp http_code
  tmp="$(mktemp "${TMPDIR:-/tmp}/nova-daily.XXXXXX")"
  http_code="$(curl -sS --connect-timeout 3 --max-time 20 -w "%{http_code}" -o "$tmp" \
    -H "Authorization: Bearer $TOKEN" "$API/api/v1/projects/active" || true)"
  if [[ "$http_code" != "200" ]]; then
    rm -f "$tmp"
    echo ""
    return 0
  fi
  python3 - "$tmp" <<'PY'
import json, sys
from pathlib import Path
raw = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
data = json.loads(raw)
print(data.get("project_root", ""))
PY
  rm -f "$tmp"
}

json_get() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
path = sys.argv[2].split(".")
value = payload
for part in path:
    if isinstance(value, list):
        value = value[int(part)]
    else:
        value = value.get(part)
print("" if value is None else value)
PY
}

step() {
  echo
  echo "→ $1"
}

cleanup() {
  if [[ -n "$PREV_ACTIVE_PROJECT" ]]; then
    api_request POST /api/v1/projects/active "{\"project_root\":\"$PREV_ACTIVE_PROJECT\"}" >/dev/null || true
  fi
  if [[ -n "$DEMO_DIR" && -d "$DEMO_DIR" ]]; then
    case "$DEMO_DIR" in
      "$SAFE_ROOT"/daily-driver-*)
        rm -rf "$DEMO_DIR"
        ;;
    esac
  fi
}
trap cleanup EXIT

echo "== NOVA Daily Driver Demo =="

step "1. Verify API"
api_request GET /api/v1/health "" >/dev/null
echo "OK: API healthy"

step "2. Verify Ollama + qwen"
runtime="$(api_request GET /api/v1/runtime/status)"
echo "$runtime" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["providers"]; print(d.get("provider_badge") or "")'
if ! curl -sf --connect-timeout 3 --max-time 10 "${NOVA_OLLAMA_BASE_URL:-http://localhost:11434}/api/tags" >/dev/null; then
  echo "FAIL: Ollama not reachable" >&2
  exit 1
fi
if ! curl -sf --connect-timeout 3 --max-time 10 "${NOVA_OLLAMA_BASE_URL:-http://localhost:11434}/api/tags" | grep -q 'qwen'; then
  echo "FAIL: qwen model not listed" >&2
  exit 1
fi

step "3. Validate paired token"
api_request GET /api/v1/runtime/status "" "$TOKEN" >/dev/null
echo "OK: paired token accepted"

step "4. Real local response to hi"
HI="$(api_request POST /api/v1/chat "{\"message\":\"hi\"}")"
echo "$HI" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["response"].strip(); assert d.get("runtime_mode") != "degraded_rule_based"; print(d["response"])'

step "5. Arbitrary question routes to local chat"
Q1="$(api_request POST /api/v1/chat "{\"message\":\"do you know Manish Sainani from Hushhh?\"}")"
echo "$Q1" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["response"].strip(); assert "I can help with status" not in d["response"]; print(d["response"])'

step "6. Set active project"
mkdir -p "$SAFE_ROOT"
DEMO_DIR="$(mktemp -d "$SAFE_ROOT/daily-driver-XXXXXX")"
mkdir -p "$DEMO_DIR"
cat >"$DEMO_DIR/README.md" <<'EOF'
# NOVA Daily Driver Demo
EOF
git -C "$DEMO_DIR" init -q
git -C "$DEMO_DIR" config user.email "demo@nova.local"
git -C "$DEMO_DIR" config user.name "NOVA Demo"
git -C "$DEMO_DIR" add README.md
git -C "$DEMO_DIR" commit -q -m "daily-driver demo"

PREV_ACTIVE_PROJECT="$(fetch_current_active_project)"
SET_PROJECT="$(api_request POST /api/v1/projects/active "{\"project_root\":\"$DEMO_DIR\"}")"
echo "$SET_PROJECT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["project_name"]); assert d["project_root"];'

step "7. Confirm project badge payload"
RUNTIME2="$(api_request GET /api/v1/runtime/status)"
echo "$RUNTIME2" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("provider_badge") or ""); assert d.get("local_available") is not None'

step "8. Search my computer for assignment"
SEARCH_PROMPT="$(api_request POST /api/v1/chat "{\"message\":\"search my computer for assignment\"}")"
CHAT_SESSION_ID="$(echo "$SEARCH_PROMPT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("session_id",""))')"
echo "$SEARCH_PROMPT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "folder choice" in d["response"].lower(); print(d["response"])'

step "9. Reply Downloads"
SEARCH_RESULT="$(api_request POST /api/v1/chat "{\"message\":\"Downloads\",\"session_id\":\"$CHAT_SESSION_ID\"}")"
echo "$SEARCH_RESULT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "Found" in d["response"] or "No matches" in d["response"]; print(d["response"])'

step "10. Confirm result and no permanent placeholder"
echo "$SEARCH_RESULT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["response"].strip() not in {"Working", "…", "..."}'

step "11. Repeat broad search"
BROAD_PROMPT="$(api_request POST /api/v1/chat "{\"message\":\"find everything related to lund on my Mac\",\"session_id\":\"$CHAT_SESSION_ID\"}")"
echo "$BROAD_PROMPT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "folder choice" in d["response"].lower(); print(d["response"])'

step "12. Reply no"
BROAD_CANCEL="$(api_request POST /api/v1/chat "{\"message\":\"no\",\"session_id\":\"$CHAT_SESSION_ID\"}")"
echo "$BROAD_CANCEL" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "cancelled" in d["response"].lower(); print(d["response"])'

step "13. Confirm cancellation"
echo "$BROAD_CANCEL" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["intent"] == "pending_cancelled"'

step "14. Protected vault search blocked"
BLOCKED="$(api_request POST /api/v1/chat "{\"message\":\"read file ~/NOVA_VAULT/secret\"}")"
echo "$BLOCKED" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["blocked"] is True; print(d["response"])'

step "15. Remember a preference"
REMEMBER="$(api_request POST /api/v1/chat "{\"message\":\"remember that my exchange files are usually in Downloads\"}")"
echo "$REMEMBER" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "remembered" in d["response"].lower(); print(d["response"])'

step "16. Ask where the files are stored"
LOOKUP="$(api_request POST /api/v1/chat "{\"message\":\"where are my exchange files usually stored?\"}")"
echo "$LOOKUP" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["response"].strip().lower() == "downloads"; print(d["response"])'

step "17. Verify remembered answer"
SUMMARY="$(api_request POST /api/v1/chat "{\"message\":\"what do you remember about me?\"}")"
echo "$SUMMARY" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "exchange files" in d["response"].lower(); print(d["response"])'

step "18. Start a new chat"
NEW_CHAT="$(api_request POST /api/v1/chat "{\"message\":\"what do you remember about me?\"}")"
echo "$NEW_CHAT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "exchange files" in d["response"].lower(); print(d["response"])'

step "19. Confirm structured preference remains"
echo "$NEW_CHAT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "downloads" in d["response"].lower()'

step "20. Verify runtime status shows actual provider"
RUNTIME3="$(api_request GET /api/v1/runtime/status)"
echo "$RUNTIME3" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("provider_badge"); print(d["provider_badge"])'

echo
echo "DEMO: PASS"
PASS=1
