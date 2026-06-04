# First live NOVA demo

Run `bash scripts/demo_live_nova.sh` for a guided checklist. This document adds operator detail.

## Prerequisites

- `make bootstrap` completed
- Docker running
- Xcode for native clients (optional for API-only steps)

## Steps

1. **Stack:** `make start && make migrate`
2. **API:** `make dev` (separate terminal)
3. **Bootstrap:** enable `NOVA_BOOTSTRAP_ADMIN_ENABLED` and set `NOVA_BOOTSTRAP_ADMIN_TOKEN` in `.env`
4. **Worker code:** `POST /api/v1/pairing/codes` with `device_type: macos_worker`
5. **Worker install:** `make install-worker` — logs at `~/Library/Logs/nova/nova-worker.stdout.log`
6. **Worker claim:** worker process claims code; operator `POST /api/v1/pairing/{id}/approve`
7. **Worker token:** worker or script calls `POST /api/v1/pairing/{id}/token` with `device_id`
8. **Client claim:** iPhone/macOS app claims client code — polls `GET /api/v1/pairing/{id}/status` until `token_ready`, then retrieves token once
9. **Mission:** tap NOVA orb → `system_status` mission
10. **Mission Room:** open mission → WebSocket ticket stream with `after_sequence` reconnect
11. **Disconnect worker:** `make worker-status` then stop worker — create mission → queued UI
12. **Reconnect:** `make worker-restart` — mission completes
13. **Revoke:** admin revokes device — pairing retrieval and API calls fail

Tokens are never printed in full by `demo_live_nova.sh`.
