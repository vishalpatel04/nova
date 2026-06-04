#!/usr/bin/env bash
set -euo pipefail

LABEL="gui/$(id -u)/com.nova.worker"
launchctl kickstart -k "$LABEL" 2>/dev/null || {
  echo "Service not loaded. Run: make install-worker" >&2
  exit 1
}
echo "Restarted com.nova.worker"
