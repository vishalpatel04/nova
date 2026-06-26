#!/usr/bin/env bash
# Voice text pipeline demo — no microphone required.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== NOVA Voice Text Pipeline Demo =="

.venv/bin/pytest tests/test_intelligent_clarifier_gmail_voice.py -q -k "voice"

export NOVA_API_TOKEN="${NOVA_API_TOKEN:-dev-token-change-me}"
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///:memory:}"

.venv/bin/python - <<'PY'
import asyncio
from nova_core.voice.pipeline import route_voice_transcript

cmd, wake = route_voice_transcript("hey nova build a todo app called voice tasks")
assert wake
assert "todo" in cmd.lower()
cmd2, _ = route_voice_transcript("nova draft an email about this app")
assert "draft" in cmd2.lower()
print("voice routing: ok")
PY

echo "DEMO: PASS"
