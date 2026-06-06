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
| POST | `/api/v1/pairing/ws-tickets` | Issue one-time `mission_events` ticket |
| WS | `/api/v1/ws/missions/{id}/events?ticket=...&after_sequence=0` | Live + replay |
| GET | `/api/v1/system/streaming-status` | Redis health |

## WebSocket protocol

1. Client authenticates over REST with a `client` token.
2. Client requests a `mission_events` WebSocket ticket bound to the mission id.
3. Client connects with `?ticket=<one_time_ticket>&after_sequence=0`.
4. Server consumes the ticket, sends historical PG events, then Redis stream entries.
5. Send `ping` → receive `pong`.
6. Send `{"type":"replay","after_sequence":5}` for missed events.

Tickets are valid for 60 seconds and cannot be replayed.

## Degraded mode

When Redis is unavailable:
- Events still persist in PostgreSQL
- `streaming: degraded` in API responses
- WebSocket receives PG history only; no fabricated live success

See [ADR-0004](adr/0004-redis-streams-mission-events.md).
