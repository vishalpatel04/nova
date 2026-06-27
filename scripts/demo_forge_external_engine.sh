#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "== NOVA Forge External Engine Demo =="
.venv/bin/pytest tests/test_external_agent_stack.py -q -k "forge or engine"
.venv/bin/python scripts/nova forge engines >/dev/null
echo "DEMO: PASS"
