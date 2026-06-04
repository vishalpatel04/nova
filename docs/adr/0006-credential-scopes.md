# ADR-0006: Separate Credential Scopes

## Status

Accepted

## Decision

Device credentials carry an explicit role: `admin`, `client`, or `worker`.

- Admin credentials manage pairing and device credential lifecycle.
- Client credentials create/read missions and subscribe to mission events.
- Worker credentials register, heartbeat, connect to worker WebSocket, and acknowledge pickup.

Route authorization checks the credential role instead of inferring authority from device type.

## Consequences

Worker tokens no longer create missions or approve/revoke devices. Client tokens no longer register or heartbeat as workers. Tests cover these boundaries.
