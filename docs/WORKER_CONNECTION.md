# Worker Connection

## Modes

| Mode | When | Transport |
|------|------|-----------|
| WebSocket | Keychain token or `WORKER_TOKEN`, `WORKER_WS_ENABLED=true` | REST ticket then `WS /api/v1/ws/worker?ticket=...` |
| REST fallback | Keychain token or `WORKER_TOKEN` | POST register + heartbeat |

## WebSocket messages (worker → API)

```json
{"type": "register", "name": "...", "device_type": "macos_worker", "capabilities": [...]}
{"type": "heartbeat", "payload": {"uptime_seconds": 120, "architecture": "arm64"}}
{"type": "mission_pickup_ack", "mission_id": "...", "command_id": "..."}
{"type": "command_pickup_ack", "command_id": "..."}
{"type": "command_result", "command_id": "...", "success": true, "result": {...}}
{"type": "ping"}
```

## API responses

```json
{"type": "connected", "device_id": "..."}
{"type": "registered", "device_id": "..."}
{"type": "heartbeat_ack", "timestamp": "..."}
{"type": "commands_assigned", "commands": [{"command_id": "...", "command_type": "system_status", "mission_id": "..."}]}
{"type": "missions_assigned", "assignments": [{"mission_id": "...", "command_id": "..."}]}
{"type": "command_pickup_acknowledged", "command_id": "..."}
{"type": "command_result_acknowledged", "command_id": "..."}
```

## Command transport

Read-only worker commands are dispatched via **Redis Streams** (`nova:worker-class:{type}:commands` or per-device streams). PostgreSQL `worker_command_assignments` is authoritative; see [SCALABLE_WORKER_DISPATCH.md](SCALABLE_WORKER_DISPATCH.md).

On connect the worker:

1. Obtains a one-time WebSocket ticket (`POST /api/v1/pairing/ws-tickets`).
2. Receives `commands_assigned` for pending stream-backed commands.
3. Sends `command_pickup_ack` then `command_result` after typed handler execution.

Worker uses bounded exponential backoff with jitter (1s → 60s max).
Queued missions are durable in PostgreSQL. On reconnect, the API re-sends unacknowledged assignments for that worker; duplicate pickup acknowledgements are idempotent and do not create duplicate `mission_started` timeline events.

## WebSocket ticket flow

```bash
curl -X POST http://localhost:8000/api/v1/pairing/ws-tickets \
  -H "Authorization: Bearer $WORKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scope":"worker"}'
```

Use the returned ticket once in `/api/v1/ws/worker?ticket=...`.

## Health endpoint

Worker health on port 9100:

```bash
curl http://localhost:9100/health
```

Returns `connection_status`, `status_report` (read-only, no shell execution).

## Pair worker locally

```bash
# 1. Create pairing code (bootstrap admin)
curl -X POST http://localhost:8000/api/v1/pairing/codes \
  -H "Authorization: Bearer $NOVA_BOOTSTRAP_ADMIN_TOKEN" \
  -d '{"device_type":"macos_worker","proposed_device_id":"m3-worker"}'

# 2. Claim + approve (see AUTH_AND_PAIRING.md)

# 3. Store the worker token in macOS Keychain and run
security add-generic-password -U \
  -s com.nova.worker \
  -a m3-worker \
  -w "$WORKER_TOKEN"
make worker
```

`DEVICE_ID` selects the Keychain account. If `WORKER_TOKEN_KEYCHAIN_ACCOUNT` is set, it overrides `DEVICE_ID`; otherwise the fallback account is `nova-worker`.

For local development only, `WORKER_TOKEN` in `.env` remains supported. Do not use plaintext `.env` worker tokens for production launchd installs.

## launchd (Slice 2C)

```bash
make install-worker
make worker-status
make worker-restart
make uninstall-worker
```

Logs: `~/Library/Logs/nova/`. See [FIRST_LIVE_DEMO.md](FIRST_LIVE_DEMO.md).

Legacy script (if present): `bash scripts/worker/install.sh`
