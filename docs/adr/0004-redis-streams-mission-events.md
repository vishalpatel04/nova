# ADR 0004: Redis Streams for Mission Event Transport

## Status

Accepted — Slice 2A

## Context

Mission timeline events must be durable (PostgreSQL) and streamable to clients with reconnect replay. Redis Pub/Sub is fire-and-forget with no persistence.

## Decision

Use **PostgreSQL as source of truth** and **Redis Streams** (`XADD`/`XRANGE`) for real-time transport and replay cursors.

- Each mission has stream key `nova:mission:{id}:events`
- Timeline rows include monotonic `sequence_number` and optional `stream_id`
- WebSocket clients receive historical PG events, then live stream entries
- Reconnect: client sends `{"type":"replay","after_sequence":N}`

If Redis is unavailable, events persist in PostgreSQL only; API returns `streaming: degraded`.

## Consequences

**Positive:** Durable replay without PG polling; ordered sequence IDs; honest degraded mode.

**Negative:** Dual-write on every event; must keep PG and stream in sync logically (stream_id on PG row).
