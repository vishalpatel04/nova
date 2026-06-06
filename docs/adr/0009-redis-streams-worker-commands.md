# ADR-0009: Redis Streams for Worker Commands

## Status

Accepted (Slice 2B Milestone A)

## Context

Mission timeline events already use Redis Streams for fanout (ADR-0004). Worker assignment was PostgreSQL-only with WebSocket notification. Multi-replica APIs and worker restarts require a transport layer that survives process restarts without duplicating side effects.

## Decision

Add Redis Streams as the **transport** for worker commands:

- Stream keys per worker device or worker class.
- `worker_command_assignments` in PostgreSQL remains authoritative for status, retries, and idempotency.
- `command_id` is the idempotency key for pickup and result acknowledgement.
- Workers execute only typed read-only command handlers; no shell bridge.

## Consequences

- API replicas can dispatch via `XADD` without shared in-memory state.
- Workers reconnect and receive `commands_assigned` after PostgreSQL reconciliation.
- Redis outage degrades transport but does not lose assignments.
- Compatible with existing `queued_missions` and mission timeline streams.
