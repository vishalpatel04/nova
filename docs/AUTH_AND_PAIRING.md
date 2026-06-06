# Authentication and Device Pairing

## Overview

Slice 2A implements token-based device pairing. Plaintext tokens are never stored in PostgreSQL.

## Flow

```mermaid
sequenceDiagram
    participant Admin
    participant API
    participant Device

    Admin->>API: POST /pairing/codes (bootstrap token)
    API-->>Admin: 6-char code + pairing_id
    Device->>API: POST /pairing/claim
    Admin->>API: POST /pairing/{id}/approve
    API-->>Device: nova_wrk_* token (once)
    Device->>API: Bearer token on all requests
```

## Endpoints

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/v1/pairing/codes` | Bootstrap admin or device |
| POST | `/api/v1/pairing/claim` | Public (rate limited) |
| POST | `/api/v1/pairing/{id}/approve` | Bootstrap admin |
| POST | `/api/v1/devices/{id}/rotate-token` | Admin |
| POST | `/api/v1/devices/{id}/revoke` | Admin |
| POST | `/api/v1/pairing/ws-tickets` | Client or worker device token |

## Development bootstrap

```bash
export NOVA_BOOTSTRAP_ADMIN_ENABLED=true
export NOVA_BOOTSTRAP_ADMIN_TOKEN=nova_bts_dev_bootstrap

curl -X POST http://localhost:8000/api/v1/pairing/codes \
  -H "Authorization: Bearer nova_bts_dev_bootstrap" \
  -H "Content-Type: application/json" \
  -d '{"device_type":"macos_worker","proposed_device_id":"my-worker"}'
```

## Token storage

- Hash: `SHA-256(NOVA_TOKEN_PEPPER:token)`
- Lookup: first 16 characters (`token_prefix`)
- States: `active`, `rotated`, `revoked`, `expired`

Plaintext device tokens and WebSocket tickets are never stored in PostgreSQL.

## Credential scopes

NOVA enforces separate credential roles:

- `admin`: pairing code creation/approval, token rotation, device revocation.
- `client`: mission creation, mission detail/timeline reads, mission event WebSockets.
- `worker`: worker registration, heartbeat, worker WebSocket, mission pickup acknowledgement.

Worker credentials cannot create missions or approve/revoke devices. Client credentials cannot register or heartbeat as workers.

## Pairing rate limits

Pairing claims are limited per source IP and per pairing code. Redis stores the counters with a TTL window. If Redis is unavailable in local development/test, NOVA falls back to an in-process limiter and emits a warning; production deployments should treat Redis unavailability as degraded.

## WebSocket tickets

Long-lived bearer tokens are not accepted in WebSocket query strings. A device authenticates over REST and requests a short-lived, one-time ticket:

```bash
curl -X POST http://localhost:8000/api/v1/pairing/ws-tickets \
  -H "Authorization: Bearer $DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scope":"worker"}'
```

Tickets expire after 60 seconds, are bound to the issuing credential/device/scope, are stored hashed, and are consumed on first successful WebSocket authentication.

## Production validation

Outside `development` and `test`, startup fails if `NOVA_TOKEN_PEPPER` is left at the development default. If bootstrap admin is enabled outside those environments, `NOVA_BOOTSTRAP_ADMIN_TOKEN` must also be changed.

See [ADR-0005](adr/0005-device-token-design.md).
