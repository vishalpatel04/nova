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

- Hash: `SHA-256(NOVA_TOKEN_PEPPER + token)`
- Lookup: first 16 characters (`token_prefix`)
- States: `active`, `rotated`, `revoked`, `expired`

See [ADR-0005](adr/0005-device-token-design.md).
