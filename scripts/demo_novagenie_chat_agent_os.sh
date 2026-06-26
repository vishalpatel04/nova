#!/usr/bin/env bash
# Demo: NOVAGenie chat endpoint returns Agent OS mission cards (not generic Qwen).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== NOVAGenie Chat Agent OS Demo =="

.venv/bin/pytest tests/test_novagenie_chat_agent_os.py -q

echo "DEMO: PASS"
