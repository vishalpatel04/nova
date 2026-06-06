#!/usr/bin/env bash
set -euo pipefail

LABEL="gui/$(id -u)/com.nova.worker"
if launchctl print "$LABEL" &>/dev/null; then
  echo "com.nova.worker: loaded"
  launchctl print "$LABEL" | rg "state =|pid =|last exit" || true
else
  echo "com.nova.worker: not loaded"
  exit 1
fi
