#!/usr/bin/env bash
# Guided local demo for NOVA Slice 2C — masks secrets in output.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mask_token() {
  local t="$1"
  if [[ ${#t} -lt 12 ]]; then echo "***"; return; fi
  echo "${t:0:8}…${t: -4}"
}

section() { echo ""; echo "==> $1"; echo ""; }

section "1. Docker services"
make start

section "2. Database migrations"
make migrate

section "3. API (run in another terminal: make dev)"
echo "Start the API with: make dev"

section "4. Bootstrap admin"
if [[ -z "${NOVA_BOOTSTRAP_ADMIN_TOKEN:-}" ]]; then
  echo "Set NOVA_BOOTSTRAP_ADMIN_ENABLED=true and NOVA_BOOTSTRAP_ADMIN_TOKEN in .env"
fi

section "5. Worker pairing code"
echo 'POST /api/v1/pairing/codes with device_type=macos_worker (Authorization: bootstrap admin)'

section "6. Install worker launchd agent"
make install-worker
make worker-status || true

section "7. Client pairing"
echo "Open iOS NOVA or macOS NOVAGenie → enter pairing code → automatic approval polling"

section "8. system_status mission"
echo "Use Chat orb or macOS hotkey (⌥ Space) to create a system_status mission"

section "9. Mission Room timeline"
echo "Open Mission Room — verify live / reconnecting / degraded badge"

section "10. Worker disconnect"
make stop
echo "Or: launchctl bootout gui/$(id -u)/com.nova.worker"

section "11. Queued mission"
echo "Create mission while worker offline — UI shows honest queued state"

section "12. Worker reconnect"
make install-worker
make worker-restart

section "13. Queued mission completion"
echo "Worker reconnects and completes queued command"

section "14. Device revocation"
echo 'POST /api/v1/devices/{id}/revoke — revoked device cannot retrieve pairing token or connect'

section "Done"
echo "See docs/FIRST_LIVE_DEMO.md for full steps."
