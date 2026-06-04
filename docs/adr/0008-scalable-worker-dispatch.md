# ADR-0008: Durable Worker Assignment

## Status

Accepted

## Decision

Worker-dependent missions are queued durably in PostgreSQL. The WebSocket is a low-latency notification and acknowledgement channel, not the source of truth.

`queued_missions.command_id` provides a deterministic idempotency key for pickup. `acknowledged_at` makes duplicate pickup acknowledgement safe. Timeline events record queued, assigned, and running transitions.

## Consequences

Queued work survives API restarts and worker reconnects. Duplicate reconnects do not execute pickup twice. Redis command streams per worker/class remain compatible with this design because PostgreSQL remains the authoritative recovery state.
