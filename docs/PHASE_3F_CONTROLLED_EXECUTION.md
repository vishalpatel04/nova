# Phase 3F — Controlled Shell Execution

Phase 3F adds a **narrow allowlist** of local shell commands that run only after explicit approval and a separate execute action.

## Flow

1. User: `run shell ls ~/Projects/nova`
2. Backend validates command against safe allowlist → creates `shell.execute` approval with fingerprint
3. User approves in **Settings → Approvals** (no auto-execute)
4. User clicks **Execute Approved Action**
5. `POST /api/v1/executions/run-approved` consumes approval atomically and runs the exact command
6. Sanitized stdout/stderr returned; stored in `shell_executions`

## Allowed commands (initial)

| Command | Notes |
|---------|-------|
| `pwd` | No arguments |
| `ls` / `ls <safe_path>` | Limited flags: `-l`, `-a`, `-1` |
| `find <safe_path>` | `-maxdepth`, `-type`, `-name` only |
| `cat` / `head` / `tail` | Single non-protected file |
| `git status` | No extra args |
| `git diff --stat` | No path args |
| `git log --oneline` | Bounded line count (max 20) |
| `make test` / `make lint` / `make typecheck` | Cwd = first allowlisted root |

## Blocked (hard — no approval)

- Destructive: `rm`, `mv`, `cp`, `chmod`, `sudo`
- Network: `curl`, `wget`, `ssh`, `scp`, `nc`
- Composition: `;`, `&&`, `\|\|`, `\|`, `>`, `$()`, backticks, newlines
- Subshells: `bash -c`, `python -c`, `eval`, `source`
- Package managers, `docker`, `brew`, `launchctl`, `osascript`
- Protected paths: vault, `.ssh`, `.env`, keys, etc.

## Security properties

- **Approval → execute separation** — approving does not run the command
- **Exact fingerprint binding** — payload `{command: "..."}` hashed at request and verify at execute
- **One-time consumption** — row lock + `FOR UPDATE` on consume; replay returns 409
- **Timeout** — 10 seconds default
- **Output bounds** — stdout/stderr excerpts max 4096 chars; secrets redacted
- **Minimal environment** — no full env dump to child process
- **Cwd** — restricted to allowlisted project root

## API

```bash
# After chat creates approval and user approves:
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"approval_id":"<uuid>"}' \
  http://localhost:8000/api/v1/executions/run-approved

# List pending + approved (actionable):
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/approvals/actionable
```

## Manual testing

1. `run shell pwd` → approval required
2. Settings → Approvals → Approve
3. Execute Approved Action → cwd path in stdout
4. `run shell ls ~/Projects/nova` → approve → execute → listing
5. `run shell rm -rf /` → hard block, no approval row
6. `run shell cat ~/.ssh/id_rsa` → hard block
7. Re-run execute on same approval → 409 consumed

## Why arbitrary shell stays disabled

Only parsed argv lists run via `subprocess` without shell interpretation. There is no `shell=True`, no pipes, and no user-defined interpreters. This prepares Phase 3G+ for worker-dispatched tools while keeping blast radius minimal on the operator Mac.
