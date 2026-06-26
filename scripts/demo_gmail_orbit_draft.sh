#!/usr/bin/env bash
# Gmail Orbit draft demo — local fallback or configured Gmail test draft only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== NOVA Gmail Orbit Draft Demo =="

.venv/bin/pytest tests/test_intelligent_clarifier_gmail_voice.py -q -k "gmail or local_draft or email"

if .venv/bin/python scripts/nova gmail status >/dev/null 2>&1; then
  echo "gmail status: ok"
else
  echo "gmail status: unavailable (expected without OAuth)"
fi

echo "DEMO: PASS"
