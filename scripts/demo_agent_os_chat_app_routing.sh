#!/usr/bin/env bash
# Demo: chat routes named app-build requests to Agent OS (never generic Qwen).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== NOVA Agent OS Chat App Routing Demo =="

.venv/bin/pytest tests/test_agent_os_chat_routing.py -q

echo "DEMO: PASS"
