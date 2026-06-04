# Troubleshooting

## WebSocket closes with 4401 or 4403

- `4401`: request a fresh WebSocket ticket with `POST /api/v1/pairing/ws-tickets`.
- `4403`: the ticket scope does not match the endpoint, mission id, or credential role.

Bearer tokens are accepted on REST endpoints only. WebSocket URLs must use one-time tickets.

## Pairing claims rate limited

Pairing attempts are limited per source IP and per code. Wait for the TTL window or use a new code. In local development/test, Redis outage falls back to an in-process limiter and logs `pairing_rate_limit_degraded_local`.

## Client pairing stuck on “waiting”

- Confirm operator called `POST /api/v1/pairing/{id}/approve`
- Poll `GET /api/v1/pairing/{id}/status` — when `token_ready` is true, client calls `POST /api/v1/pairing/{id}/token` once
- Expired or rejected pairings require a new code

## macOS hotkey conflict

If **⌥ S** does not summon NOVA, another app may own the combination. Disable hotkey in NOVA Settings or change modifiers (future slice).

## Redis unavailable

Mission timelines remain durable in PostgreSQL. APIs report `streaming: degraded`, and WebSocket replay falls back to PostgreSQL history.

## Queued mission does not start

Check:

- worker device has an active `worker` credential
- worker requested a `worker` WebSocket ticket
- worker sent `mission_pickup_ack` with the assigned `command_id`
- device is not revoked

## API won't start

```bash
make doctor
docker compose -f infra/docker-compose.yml ps
```

## 401 Unauthorized

- Ensure `Authorization: Bearer <token>` header is set
- For dev: `NOVA_REQUIRE_DEVICE_TOKEN=false` or use paired device token
- Bootstrap admin: `NOVA_BOOTSTRAP_ADMIN_ENABLED=true`

## Mission queued instead of running

Expected when no worker is online. Message:

> Worker is offline. Your mission is queued and will start when an eligible worker reconnects.

Fix: start worker with valid `WORKER_TOKEN` and send heartbeat.

## Redis degraded streaming

Check Redis: `docker compose -f infra/docker-compose.yml exec redis redis-cli ping`

Events still persist in PostgreSQL; timeline GET works without Redis.

## Worker WebSocket disconnects

Check worker logs: `/tmp/nova-worker.stderr.log`

Verify token not revoked: `POST /api/v1/devices/{id}/revoke` removes access.

## Migrations

```bash
make migrate
# or
.venv/bin/alembic upgrade head
```

## Simulate disconnect / reconnect

1. Start worker with WebSocket mode
2. Stop worker (`Ctrl+C` or `launchctl unload`)
3. Create mission → should queue
4. Restart worker → queued mission picked up

## Plist validation

```bash
plutil -lint infra/launchd/com.nova.worker.plist
```
