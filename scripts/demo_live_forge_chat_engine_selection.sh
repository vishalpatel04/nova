#!/usr/bin/env bash
# Live Forge engine selection via NOVAGenie chat.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== NOVA Live Forge Chat Engine Selection Demo =="

.venv/bin/pytest tests/test_live_forge_engine_selection.py -q

echo "DEMO: PASS"
