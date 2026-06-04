# Worker Connection

## Modes

| Mode | When | Transport |
|------|------|-----------|
| WebSocket | `WORKER_TOKEN` set, `WORKER_WS_ENABLED=true` | REST ticket then `WS /api/v1/ws/worker?ticket=...` |
| REST fallback | Worker token | POST register + heartbeat |

## WebSocket messages (worker → API)

```json
{"type": "register", "name": "...", "device_type": "macos_worker", "capabilities": [...]}
{"type": "heartbeat", "payload": {"uptime_seconds": 120, "architecture": "arm64"}}
{"type": "mission_pickup_ack", "mission_id": "...", "command_id": "..."}
{"type": "ping"}
```

## API responses

```json
{"type": "connected", "device_id": "..."}
{"type": "registered", "device_id": "..."}
{"type": "heartbeat_ack", "timestamp": "..."}
{"type": "missions_assigned", "assignments": [{"mission_id": "...", "command_id": "..."}]}
{"type": "mission_pickup_acknowledged", "mission_id": "..."}
```

## Reconnect

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

# 3. Set WORKER_TOKEN in .env and run
make worker
```

## launchd

```bash
bash scripts/worker/install.sh
```
