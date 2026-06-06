#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DERIVED_DATA="/private/tmp/nova-macos-manual"
PROJECT="$ROOT/apps/macos/NOVAGenie.xcodeproj"
APP="$DERIVED_DATA/Build/Products/Debug/NOVAGenie.app"

echo "Killing existing NOVAGenie processes..."
pkill -x NOVAGenie 2>/dev/null || true
sleep 1

remaining="$(pgrep -x NOVAGenie || true)"
if [[ -n "$remaining" ]]; then
  echo "ERROR: Existing NOVAGenie processes are still running:"
  pgrep -fal NOVAGenie
  exit 1
fi

echo "Building NOVAGenie into $DERIVED_DATA..."
rm -rf "$DERIVED_DATA"
xcodebuild \
  -project "$PROJECT" \
  -scheme NOVAGenie \
  -destination 'platform=macOS' \
  -derivedDataPath "$DERIVED_DATA" \
  build

if [[ ! -d "$APP" ]]; then
  echo "ERROR: Build succeeded but app bundle was not found at $APP"
  exit 1
fi

echo "Launching NOVAGenie..."
open "$APP"
sleep 2

pids="$(pgrep -x NOVAGenie || true)"
pid_count="$(printf '%s\n' "$pids" | sed '/^$/d' | wc -l | tr -d ' ')"
if [[ "$pid_count" -ne 1 ]]; then
  echo "ERROR: Expected exactly one NOVAGenie process, found $pid_count:"
  pgrep -fal NOVAGenie || true
  exit 1
fi

echo "Active NOVAGenie PID: $pids"
echo "Expected menu-bar actions: Open NOVA, Pair Device, Settings, Quit NOVA"
echo "Optional shortcut: Control + Option + Space"
echo "Inspect structured NOVA logs with:"
echo "log show --style compact --last 3m --predicate 'process == \"NOVAGenie\"' | grep -E 'nova_'"
