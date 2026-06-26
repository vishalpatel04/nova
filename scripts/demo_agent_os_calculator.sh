#!/usr/bin/env bash
# Investor demo: deterministic calculator Agent OS mission.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WORKSPACE="${NOVA_WORKSPACE_ROOT:-$HOME/Projects/nova-workspace}"
CALC="$WORKSPACE/calculator-app"

echo "== NOVA Agent OS Calculator Demo =="

if [[ -d "$CALC" ]]; then
  echo "Cleaning previous calculator workspace..."
  rm -rf "$CALC"
fi

OUTPUT=$(NOVA_WORKSPACE_ROOT="$WORKSPACE" .venv/bin/python scripts/nova mission \
  "build a calculator app, test it, preview it, and prepare deployment" 2>&1)
echo "$OUTPUT"

MISSION_ID=$(echo "$OUTPUT" | grep -Eo '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | tail -1)
test -n "$MISSION_ID"

for agent in Prime Archive Forge "Product Planner" Architect "Frontend Engineer" "QA Engineer" "Code Reviewer" "Deploy Engineer" Sentry; do
  echo "$OUTPUT" | grep -q "\[$agent\]" || { echo "Missing timeline agent: $agent"; exit 1; }
done

test -f "$CALC/package.json"
test -f "$CALC/src/App.tsx"
test -f "$CALC/src/calculator.ts"
grep -q '"react"' "$CALC/package.json"
echo "$OUTPUT" | grep -qi "build: PASS"
echo "$OUTPUT" | grep -qi "http://127.0.0.1:"
echo "$OUTPUT" | grep -qi "approval required"
test -f "$WORKSPACE/.nova-runs/${MISSION_ID}.json"

echo "DEMO: PASS"
