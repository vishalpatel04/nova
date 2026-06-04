# Realtime Mission Events

## Architecture

```
Workflow → publish_timeline_event()
              ├─ PostgreSQL (timeline_events + sequence_number)
              └─ Redis Stream (nova:mission:{id}:events)
                     └─ WebSocket clients
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/missions/{id}/timeline` | Durable timeline with sequence numbers |
| WS | `/api/v1/ws/missions/{id}/events?token=...&after_sequence=0` | Live + replay |
| GET | `/api/v1/system/streaming-status` | Redis health |

## WebSocket protocol

1. Connect with `?token=<device_token>&after_sequence=0`
2. Server sends historical PG events, then Redis stream entries
3. Send `ping` → receive `pong`
4. Send `{"type":"replay","after_sequence":5}` for missed events

## Degraded mode

When Redis is unavailable:
- Events still persist in PostgreSQL
- `streaming: degraded` in API responses
- WebSocket receives PG history only; no fabricated live success

See [ADR-0004](adr/0004-redis-streams-mission-events.md).
