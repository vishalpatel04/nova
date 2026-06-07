# Milestone 2 — Background Agent Mode

Safe, recurring background tasks with local notifications. Background work uses predefined task types only — no arbitrary shell, no auto-patch apply, no webhooks.

## Task model

`background_tasks` stores device-scoped schedules:

| Field | Description |
|-------|-------------|
| `task_type` | Allowlisted safe type (see below) |
| `schedule_kind` | `once`, `interval`, or `cron` |
| `schedule_expression` | ISO8601 (once), `6h`/`30m` (interval), daily cron `M H * * *` |
| `status` | `active`, `paused`, `running`, `succeeded`, `failed`, `cancelled` |
| `next_run_at` | Next scheduled execution |
| `project_root` | Required for repo-scoped tasks; validated against allowlist |

Each run is recorded in `background_task_runs` with bounded evidence excerpts.

## Supported task types

| Type | Scope | Behavior |
|------|-------|----------|
| `repo.health_check` | Project | Safe validation command |
| `repo.run_validation` | Project | Same validation pipeline as Milestone 1 |
| `repo.inspect` | Project | Read-only repo inspection |
| `project.summary` | Project | Short project summary |
| `system.status` | System | Worker availability summary |
| `reminder.note` | Reminder | Safe text reminder from `prompt` |

Blocked: shell payloads, patch apply, git push, browser, webhooks, n8n.

## Scheduler lifecycle

1. API lifespan starts a poll loop (default **30s**).
2. Due `active` tasks with `next_run_at <= now` are **claimed** atomically (`active` → `running`).
3. Predefined executor runs safe workflow (revalidates project policy).
4. Run row + audit events recorded (`background_task.claimed`, `.started`, `.succeeded`/`.failed`).
5. Recurring tasks return to `active` with updated `next_run_at`.
6. `once` tasks end as `succeeded` or `failed`.
7. Transient errors retry with exponential backoff (max **3** attempts, base **60s**).
8. On shutdown, loop cancels gracefully; stale `running` tasks reset to `active` on next tick.

## Notification lifecycle

`notification_items` is device-scoped inbox:

| Type | When |
|------|------|
| `task.succeeded` | Generic task success |
| `task.failed` | Generic task failure |
| `validation.failed` | Validation exit ≠ 0 |
| `validation.recovered` | Validation success after prior failure |
| `reminder` | Reminder task fired |

Summaries are sanitized — no tokens, secrets, or protected path content.

## Schedule examples

```json
{"schedule_kind":"cron","schedule_expression":"0 9 * * *"}
{"schedule_kind":"interval","schedule_expression":"6h"}
{"schedule_kind":"once","schedule_expression":"2026-06-03T09:00:00+00:00"}
```

Chat shortcuts:

- `create daily repo check at 9am`
- `create repo validation every 6 hours`
- `background tasks` / `notifications`
- `pause task <id>` / `resume task <id>` / `cancel task <id>`
- `run task <id> now`

## API

| Method | Path |
|--------|------|
| GET | `/api/v1/background-tasks` |
| POST | `/api/v1/background-tasks` |
| GET | `/api/v1/background-tasks/{id}` |
| POST | `/api/v1/background-tasks/{id}/pause` |
| POST | `/api/v1/background-tasks/{id}/resume` |
| POST | `/api/v1/background-tasks/{id}/cancel` |
| GET | `/api/v1/background-tasks/{id}/runs` |
| POST | `/api/v1/background-tasks/{id}/run-now` |
| GET | `/api/v1/background-tasks/scheduler-status` |
| GET | `/api/v1/notifications` |
| POST | `/api/v1/notifications/{id}/read` |
| POST | `/api/v1/notifications/read-all` |

Ownership: `user_id` + `device_id`. Revoked devices rejected. Cross-device access denied.

## Startup

```bash
make start
make migrate
make dev          # API + background scheduler loop
make worker       # optional local worker
```

## Run-now flow

1. Client POST `/background-tasks/{id}/run-now`
2. Atomic claim (must be `active`, not paused/cancelled)
3. Safe executor runs immediately
4. Notifications emitted on failure/recovery
5. Recurring schedule `next_run_at` recalculated

Validation failures may surface patch proposals via Milestone 1 chat — **never** auto-applied from background tasks.

## Safety boundaries

- Predefined task types only
- Project root validation + protected paths blocked
- One active run per task (claim CAS)
- Bounded retries for transient errors only
- Audit trail for all scheduler events
- No unrestricted shell, push, browser, webhooks, auto-patch

## macOS UX

Settings → **Background** and **Notifications** tabs. Menu bar shows scheduler status, active/failed task counts, unread badge.

## Demo

```bash
export NOVA_DEMO_TOKEN=<paired-client-token>   # optional
./scripts/demo_background_agent.sh
```

## Limitations

- Daily cron only (`M H * * *`); arbitrary cron rejected
- Scheduler runs in API process (not separate worker daemon)
- No APNs / remote push
- Phase 3C legacy scheduler remains audit-only (separate from background tasks)
- Worker dispatch optional; in-process executor uses same policy gates as worker commands

## Migration

`0010_milestone_2_background_agent` — creates `background_tasks`, `background_task_runs`, `notification_items`.
