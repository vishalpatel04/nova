# Worker Connection

## Modes

| Mode | When | Transport |
|------|------|-----------|
| WebSocket | `WORKER_TOKEN` set, `WORKER_WS_ENABLED=true` | `WS /api/v1/ws/worker?token=...` |
| REST fallback | No token | POST register + heartbeat |

## WebSocket messages (worker → API)

```json
{"type": "register", "name": "...", "device_type": "macos_worker", "capabilities": [...]}
{"type": "heartbeat", "payload": {"uptime_seconds": 120, "architecture": "arm64"}}
{"type": "ping"}
```

## API responses

```json
{"type": "connected", "device_id": "..."}
{"type": "registered", "device_id": "..."}
{"type": "heartbeat_ack", "timestamp": "..."}
{"type": "missions_assigned", "mission_ids": ["..."]}
```

## Reconnect

Worker uses bounded exponential backoff with jitter (1s → 60s max).

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
