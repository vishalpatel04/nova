# ADR 0005: Device Token Design

## Status

Accepted — Slice 2A

## Context

Clients and workers authenticate via long-lived device tokens. Plaintext secrets must never be stored in PostgreSQL.

## Decision

- Token format: `nova_{cli|wrk|adm|bts}_{urlsafe_random}`
- Store **SHA-256(pepper + token)** and **16-char prefix** for lookup
- Pepper from `NOVA_TOKEN_PEPPER` environment variable
- Pairing flow: short-lived 6-char hex code → claim → optional approval → one-time credential issuance
- Rotation: mark old credentials `rotated`, issue new
- Revocation: mark device + credentials `revoked`, record in `token_revocations`

Bootstrap admin token (`NOVA_BOOTSTRAP_ADMIN_ENABLED`) for development only.

## Consequences

**Positive:** No plaintext in DB; prefix lookup avoids scanning; rotation and revocation are auditable.

**Negative:** Pepper compromise requires re-hash migration; tokens cannot be recovered after issuance (by design).
