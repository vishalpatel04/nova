# Scalable Worker Dispatch

Slice 2A uses PostgreSQL as the durable source of truth for worker-dependent mission assignment.

## Durable state

`queued_missions` records:

- mission id
- required worker device types
- assigned worker device id
- deterministic command id
- assigned timestamp
- acknowledged timestamp

Mission creation records `queued_waiting_for_worker` when no eligible worker is online. The timeline records the queued state honestly.

## Assignment flow

1. Client creates a worker-dependent mission.
2. API stores the mission and `queued_missions` row in PostgreSQL.
3. Worker connects with a one-time WebSocket ticket.
4. API assigns unacknowledged queued missions to the worker and sends `missions_assigned`.
5. Worker sends `mission_pickup_ack` with `mission_id` and `command_id`.
6. API marks the mission `running` and records a `mission_started` timeline event.

Duplicate reconnects and duplicate pickup acknowledgements reuse the same command id and do not create duplicate `mission_started` events.

## Redis Streams

Redis Streams are used for mission timeline fanout. The durable worker assignment state is PostgreSQL-backed in Slice 2A. A future dispatch worker can add Redis command streams per worker/class using the existing `command_id` as the idempotency key; PostgreSQL remains authoritative for redelivery and recovery.

## Recovery behavior

- API restart: queued/assigned/unacknowledged missions remain in PostgreSQL.
- Worker disconnect: unacknowledged assignments can be re-sent on reconnect.
- Duplicate messages: `command_id` and `acknowledged_at` make pickup acknowledgement idempotent.
- Redis unavailable: timeline events remain durable in PostgreSQL and streaming reports degraded mode.
