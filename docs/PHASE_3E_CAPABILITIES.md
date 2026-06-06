# Phase 3E — Capability Model & Approvals

Phase 3E adds an explicit **capability system** and **approval workflow** so NOVA can safely gate stronger tools before execution is wired.

## Capability model

| Capability | Default | Notes |
|------------|---------|-------|
| `file.read` | Allowed | Non-protected paths only |
| `shell.preview` | Allowed | Command preview in chat |
| `shell.execute` | Approval required | No execution until approved + future worker path |
| `file.write` | Approval required | Includes delete-file requests |
| `code.patch` | Approval required | Shows patch plan summary |
| `cloud.send_file` | Approval required | Cloud providers cannot receive file bytes without approval |
| `git.commit` | Approval required | Scaffold |
| `automation.run` | Blocked | n8n/OpenClaw scaffold only |
| `browser.control` | Blocked | Not enabled |
| `git.push` | Blocked | Not enabled |

Protected paths (`~/NOVA_VAULT`, `~/.ssh`, `.env`, keys, etc.) **never** accept approval override in Phase 3E.

## Approval lifecycle

1. User requests unsafe action in chat (e.g. `run shell ls`).
2. Backend creates `approval_requests` row — status `pending`, TTL 30 minutes.
3. Chat responds: **"I can do this after approval."** with summary, risk, preview, approval ID.
4. macOS **Settings → Approvals** lists pending items; user taps Approve or Reject.
5. Approved requests are **one-time use** (`consumed` after execution — execution path coming in a later phase).
6. Expired pending requests cannot be approved.

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/approvals/request` | Create approval (also used internally from chat) |
| GET | `/api/v1/approvals/pending` | List own pending approvals |
| POST | `/api/v1/approvals/{id}/approve` | Approve |
| POST | `/api/v1/approvals/{id}/reject` | Reject |

Ownership is enforced by `user_id` + `device_id`. Action fingerprint must match on consume.

## Audit events

- `approval.requested`
- `approval.approved`
- `approval.rejected`
- `approval.expired`
- `approval.consumed`

## Current blocked capabilities

- Real shell execution (even after approval — state updates only)
- n8n / OpenClaw execution
- Browser automation
- git push
- Protected path access

## Preparing for future automation

Approvals store capability, fingerprinted payload, risk level, and preview text. When worker execution lands, the flow will be:

1. Chat creates approval → user approves → chat/worker calls `consume()` with matching fingerprint → tool runs once.

## Manual test commands

```bash
# Shell → pending approval
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"run shell ls"}' http://localhost:8000/api/v1/chat

# List pending
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/approvals/pending

# Approve
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/approvals/{id}/approve

# Protected path — still blocked, no approval
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"read file ~/.ssh/id_rsa"}' http://localhost:8000/api/v1/chat

# Write file → approval
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"write file test.txt"}' http://localhost:8000/api/v1/chat
```

macOS: open NOVAGenie → Settings → **Approvals** tab.
