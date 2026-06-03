#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLIST_SRC="$ROOT/infra/launchd/com.nova.worker.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.nova.worker.plist"

sed "s|__NOVA_ROOT__|$ROOT|g" "$PLIST_SRC" > "$PLIST_DST"

launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo "NOVA worker installed and loaded: $PLIST_DST"
echo "Logs: /tmp/nova-worker.stdout.log"
