#!/usr/bin/env bash
# Investor demo: deterministic calculator Agent OS mission with verified preview.
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
echo "$OUTPUT" | grep -qi "Build: PASS"
PREVIEW_URL=$(echo "$OUTPUT" | grep -Eo 'http://127\.0\.0\.1:[0-9]+' | head -1)
test -n "$PREVIEW_URL"
curl -sf "$PREVIEW_URL" >/dev/null
echo "$OUTPUT" | grep -qi "Deploy this app?"
echo "$OUTPUT" | grep -qi "yes"
echo "$OUTPUT" | grep -qi "no"
test -f "$WORKSPACE/.nova-runs/${MISSION_ID}.json"

NOVA_WORKSPACE_ROOT="$WORKSPACE" .venv/bin/python scripts/nova stop-preview "$MISSION_ID" >/dev/null || true

echo "DEMO: PASS"
