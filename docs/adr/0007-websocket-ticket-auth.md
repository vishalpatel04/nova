# ADR-0007: WebSocket Ticket Authentication

## Status

Accepted

## Decision

WebSocket endpoints require short-lived, one-time tickets issued by an authenticated REST request. Long-lived bearer tokens are not accepted in WebSocket query strings.

Tickets are hashed in PostgreSQL, bound to the issuing device credential, scope, and mission id when applicable. A ticket expires after 60 seconds and is consumed on first successful authentication.

## Consequences

Swift clients can use a simple URL query parameter without exposing durable credentials in logs, browser history, proxies, or crash diagnostics. Replay attempts fail because consumed tickets are no longer active.
