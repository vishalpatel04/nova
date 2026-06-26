#!/usr/bin/env bash
# End-to-end investor demo backend checks.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== NOVA Investor End-to-End Demo =="

.venv/bin/pytest tests/test_investor_demo_flow.py tests/test_intelligent_clarifier_gmail_voice.py -q
.venv/bin/pytest tests/test_novagenie_chat_agent_os.py -q

echo "DEMO: PASS"
