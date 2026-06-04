# Troubleshooting

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
