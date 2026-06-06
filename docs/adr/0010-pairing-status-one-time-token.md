# ADR-0010: Pairing status and one-time token retrieval

## Status

Accepted — Slice 2C

## Context

Manual token paste after operator approval was a temporary Slice 2B UX.

## Decision

- `GET /api/v1/pairing/{pairing_id}/status` exposes `pending`, `approved`, `claimed`, `expired`, `rejected`
- Approved pairings store the device bearer token in Redis (or in-memory fallback) until `POST /api/v1/pairing/{pairing_id}/token` consumes it once
- PostgreSQL never stores plaintext tokens; credentials remain hashed in `device_credentials`
- Rate limits on status polls and token retrieval; audit events on approve, reject, and retrieve

## Consequences

- Approve endpoint no longer returns the bearer token to operators
- Demo scripts must call token retrieval explicitly for workers
