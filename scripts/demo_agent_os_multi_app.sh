#!/usr/bin/env bash
# Demo: multi-app Agent OS builder (todo, habit tracker, landing page).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WORKSPACE="${NOVA_WORKSPACE_ROOT:-/tmp/nova-multi-app-demo}"
export NOVA_WORKSPACE_ROOT="$WORKSPACE"

echo "== NOVA Agent OS Multi-App Demo =="

run_build() {
  local request="$1"
  local dir_name="$2"
  local project="$WORKSPACE/$dir_name"
  if [[ -d "$project" ]]; then
    rm -rf "$project"
  fi
  OUTPUT=$(.venv/bin/python scripts/nova mission "$request" 2>&1)
  echo "$OUTPUT"
  echo "$OUTPUT" | grep -qi "Build: PASS" || { echo "Build failed for $request"; exit 1; }
  echo "$OUTPUT" | grep -qi "Deploy this app?" || { echo "Missing deploy prompt for $request"; exit 1; }
  test -f "$project/package.json"
  test -f "$project/src/App.tsx"
  MISSION_ID=$(echo "$OUTPUT" | grep -Eo '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | tail -1)
  .venv/bin/python scripts/nova stop-preview "$MISSION_ID" >/dev/null || true
}

run_build "build a todo app" "todo-app"
run_build "build a habit tracker app" "habit-tracker-app"
run_build "build a landing page for SusCo" "landing-page-susco"

echo "DEMO: PASS"
