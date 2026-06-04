#!/usr/bin/env bash
# Install nova-worker as a per-user launchd agent (no Terminal required after install).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$ROOT/infra/launchd/com.nova.worker.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.nova.worker.plist"
LOG_DIR="$HOME/Library/Logs/nova"

if [[ ! -f "$ROOT/.venv/bin/python" ]]; then
  echo "Run 'make bootstrap' first (.venv missing)." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
sed "s|__NOVA_ROOT__|$ROOT|g" "$PLIST_SRC" | sed "s|/tmp/nova-worker|$LOG_DIR/nova-worker|g" > "$PLIST_DST"

launchctl bootout "gui/$(id -u)/com.nova.worker" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/com.nova.worker"
echo "Installed com.nova.worker → $PLIST_DST"
echo "Logs: $LOG_DIR/nova-worker.stdout.log"
