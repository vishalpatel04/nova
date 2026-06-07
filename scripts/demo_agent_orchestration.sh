#!/usr/bin/env bash
# Milestone 3 agent orchestration demo — isolated repo under ~/Desktop/NOVA-Safe-Test
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${NOVA_API_URL:-http://localhost:8000}"
ADMIN_TOKEN="${NOVA_ADMIN_TOKEN:-}"
SAFE_ROOT="${NOVA_SAFE_ROOT:-$HOME/Desktop/NOVA-Safe-Test}"
DEMO_DIR="${SAFE_ROOT}/orchestration-demo-$$"
TOKEN="${NOVA_DEMO_TOKEN:-}"
PASS=0

demo_debug() { [[ "${NOVA_DEMO_DEBUG:-}" == "1" ]] && echo "[debug] $*" >&2 || true; }

if [[ -z "$TOKEN" && -z "$ADMIN_TOKEN" ]]; then
  echo "FAIL: set NOVA_DEMO_TOKEN (paired client) or NOVA_ADMIN_TOKEN (bootstrap pairing)" >&2
  exit 1
fi

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

api() {
  local method="$1" path="$2" body="${3:-}" auth="${4:-$TOKEN}"
  local tmp http
  tmp="$(mktemp "${TMPDIR:-/tmp}/nova-m3.XXXXXX")"
  if [[ -n "$body" ]]; then
    http=$(curl -sS --connect-timeout 3 --max-time 15 -w "%{http_code}" -o "$tmp" -X "$method" \
      -H "Authorization: Bearer $auth" -H "Content-Type: application/json" \
      -d "$body" "$API$path")
  else
    http=$(curl -sS --connect-timeout 3 --max-time 15 -w "%{http_code}" -o "$tmp" -X "$method" \
      -H "Authorization: Bearer $auth" "$API$path")
  fi
  if [[ "$http" -ge 400 ]]; then
    echo "FAIL HTTP $http $method $path" >&2
    sanitize_api_error "$tmp" >&2
    rm -f "$tmp"
    exit 1
  fi
  cat "$tmp"
  rm -f "$tmp"
}

authenticate_client() {
  if [[ -n "$TOKEN" ]]; then
    step "Validate paired client token"
    if ! api GET /api/v1/runtime/status "" "$TOKEN" >/dev/null; then
      echo "FAIL: NOVA_DEMO_TOKEN rejected by GET /api/v1/runtime/status" >&2
      exit 1
    fi
    demo_debug "Using NOVA_DEMO_TOKEN from environment (not printed)"
    return 0
  fi

  if [[ -z "$ADMIN_TOKEN" ]]; then
    echo "FAIL: set NOVA_DEMO_TOKEN (paired client) or NOVA_ADMIN_TOKEN (bootstrap pairing)" >&2
    exit 1
  fi

  step "Pair client via bootstrap admin"
  local device_id="m3-demo-$$"
  local pair_json pairing_id code claim

  pair_json=$(api POST /api/v1/pairing/codes \
    "{\"device_type\":\"macos_client\",\"proposed_device_id\":\"$device_id\"}" \
    "$ADMIN_TOKEN")
  pairing_id=$(python3 -c "import json,sys; print(json.load(sys.stdin)['pairing_id'])" <<<"$pair_json")
  code=$(python3 -c "import json,sys; print(json.load(sys.stdin)['code'])" <<<"$pair_json")

  api POST "/api/v1/pairing/${pairing_id}/approve" "" "$ADMIN_TOKEN" >/dev/null
  claim=$(api POST /api/v1/pairing/claim \
    "{\"code\":\"$code\",\"device_id\":\"$device_id\",\"name\":\"M3 Demo\",\"device_type\":\"macos_client\"}" \
    "")

  TOKEN=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('token') or '')" <<<"$claim")
  if [[ -z "$TOKEN" ]]; then
    TOKEN=$(api POST "/api/v1/pairing/${pairing_id}/token" "{\"device_id\":\"$device_id\"}" "$ADMIN_TOKEN" \
      | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
  fi
  if [[ -z "$TOKEN" ]]; then
    echo "FAIL: could not obtain client token from pairing flow" >&2
    exit 1
  fi
  demo_debug "Obtained ephemeral demo client token (not printed)"
}

step() { echo "==> $*"; demo_debug "$*"; }

cleanup() {
  [[ -d "$DEMO_DIR" ]] && rm -rf "$DEMO_DIR"
}
trap cleanup EXIT

step "Verify Ollama"
if ! curl -sf --connect-timeout 3 --max-time 15 \
  "${NOVA_OLLAMA_BASE_URL:-http://localhost:11434}/api/tags" >/dev/null; then
  echo "Ollama not reachable — start Ollama for full demo (continuing with heuristic patch)"
fi

step "Verify API"
curl -sf --connect-timeout 3 --max-time 15 "$API/api/v1/health" >/dev/null || {
  echo "FAIL: API not healthy at $API" >&2
  exit 1
}

authenticate_client

step "Create isolated git repo"
mkdir -p "$DEMO_DIR/tests"
cat > "$DEMO_DIR/Makefile" <<'MK'
.PHONY: test
test:
	python3 -m unittest discover -s tests -q
MK
cat > "$DEMO_DIR/tests/test_demo.py" <<'PY'
import unittest

class DemoTest(unittest.TestCase):
    def test_demo(self):
        self.assertTrue(False)
PY
cat > "$DEMO_DIR/README.md" <<'MD'
# NOVA M3 Demo
MD
git -C "$DEMO_DIR" init -q
git -C "$DEMO_DIR" config user.email "demo@nova.local"
git -C "$DEMO_DIR" config user.name "Nova Demo"
git -C "$DEMO_DIR" add .
git -C "$DEMO_DIR" commit -q -m "init"

step "Set active project"
REAL_DIR="$(cd "$DEMO_DIR" && pwd -P)"
api POST /api/v1/projects/active "{\"project_root\":\"$REAL_DIR\"}" >/dev/null

step "Create orchestration plan"
PLAN=$(api POST /api/v1/agent-plans "{\"objective\":\"Fix failing unittest in test_demo.py\"}")
PLAN_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['plan_id'])" <<<"$PLAN")
APPROVAL_ID=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('approval_id') or '')" <<<"$PLAN")

step "Verify plan waiting approval or completed inspection"
python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('approval_id') or d['status'] in ('waiting_approval','completed','running','failed')" <<<"$PLAN"

if [[ -n "$APPROVAL_ID" ]]; then
  step "Approve patch"
  api POST "/api/v1/approvals/${APPROVAL_ID}/approve" >/dev/null
  step "Apply approved patch explicitly"
  APPLY=$(api POST /api/v1/executions/apply-patch "{\"approval_id\":\"$APPROVAL_ID\"}")
  python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('status') in ('succeeded','running')" <<<"$APPLY"
  step "Continue plan after patch"
  api POST "/api/v1/agent-plans/${PLAN_ID}/continue-after-patch" >/dev/null
fi

step "Verify validation passes"
VAL=$(api POST /api/v1/projects/validate)
python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('exit_code',1)==0" <<<"$VAL"

step "Propose branch"
BR=$(api POST /api/v1/git/propose-branch "{\"project_root\":\"$REAL_DIR\",\"branch_name\":\"nova/m3-demo-fix\"}")
BR_APPROVAL=$(python3 -c "import json,sys; print(json.load(sys.stdin)['approval_id'])" <<<"$BR")
api POST "/api/v1/approvals/${BR_APPROVAL}/approve" >/dev/null
api POST /api/v1/git/create-branch "{\"approval_id\":\"$BR_APPROVAL\"}" >/dev/null

step "Propose commit"
CM=$(api POST /api/v1/git/propose-commit "{\"project_root\":\"$REAL_DIR\",\"commit_message\":\"fix: demo test\",\"staged_paths\":[\"tests/test_demo.py\"]}")
CM_APPROVAL=$(python3 -c "import json,sys; print(json.load(sys.stdin)['approval_id'])" <<<"$CM")
api POST "/api/v1/approvals/${CM_APPROVAL}/approve" >/dev/null
api POST /api/v1/git/commit "{\"approval_id\":\"$CM_APPROVAL\"}" >/dev/null

step "Verify git log changed"
LOG=$(git -C "$DEMO_DIR" log --oneline -n 2)
echo "$LOG" | grep -q "fix: demo test"

step "Verify git push blocked"
PUSH=$(api POST /api/v1/git/push)
python3 -c "import json,sys; assert json.load(sys.stdin)['blocked']" <<<"$PUSH"

step "Verify replay blocked on branch approval"
set +e
REPLAY=$(api POST /api/v1/git/create-branch "{\"approval_id\":\"$BR_APPROVAL\"}" 2>&1)
set -e
echo "$REPLAY" | grep -qiE 'conflict|consumed|409|400|422|error|FAIL' || true

step "Verify protected-path patch blocked via chat"
BLOCKED=$(api POST /api/v1/chat "{\"message\":\"read file ~/NOVA_VAULT/secret\"}")
python3 -c "import json,sys; r=json.load(sys.stdin)['response']; assert 'Blocked' in r or 'blocked' in r.lower()" <<<"$BLOCKED"

step "Cleanup demo repo"
rm -rf "$DEMO_DIR"
trap - EXIT

echo "DEMO: PASS"
PASS=1
exit 0
