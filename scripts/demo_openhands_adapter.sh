#!/usr/bin/env bash
# OpenHands adapter demo — fallback to deterministic_template when unavailable.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "== NOVA OpenHands Adapter Demo =="
.venv/bin/python - <<'PY'
from apps.api.services.forge_engine_service import ForgeEngineService

svc = ForgeEngineService()
status = {r["engine_id"]: r["available"] for r in svc.engines_status()}
if not status.get("openhands"):
    print("OpenHands unavailable — setup hint shown, using fallback.")
out = svc.run("build a calculator app named demo-oh", engine_id="openhands")
print(f"engine={out['engine_id']} success={out['result']['success']}")
assert out["result"]["success"] or out["result"].get("fallback_used")
print("DEMO: PASS")
PY
