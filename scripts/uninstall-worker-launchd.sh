#!/usr/bin/env bash
set -euo pipefail

PLIST_DST="$HOME/Library/LaunchAgents/com.nova.worker.plist"
launchctl bootout "gui/$(id -u)/com.nova.worker" 2>/dev/null || true
rm -f "$PLIST_DST"
echo "Uninstalled com.nova.worker"
