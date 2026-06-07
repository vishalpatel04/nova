# Milestone 1: Useful Local Coding Agent

NOVA can inspect an active project, run safe validation, propose a patch, require approval, apply the patch only after explicit user action, and re-run validation.

## Active project model

One active project per paired **device** (`active_projects` table):

| Field | Description |
|-------|-------------|
| `project_root` | Resolved path under `policies.yaml` allowlist |
| `project_name` | Directory basename |
| `current_branch` | From `git branch --show-current` when available |
| `detected_tooling` | Python/Makefile/iOS/docs/tests flags |
| `last_opened_at` | Updated on each `set project` |

Chat commands:

- `set project ~/Projects/nova`
- `current project`
- `inspect repo`
- `summarize repo`

API:

- `POST /api/v1/projects/active` — set active project
- `GET /api/v1/projects/active` — current project
- `POST /api/v1/projects/inspect` — bounded repo inspection
- `POST /api/v1/projects/validate` — safe `make test` (or detected command)

Project root rules:

- Must be under configured `safe_filesystem.allowed_roots`
- Protected paths (vault, `.env`, credentials) rejected
- Symlink escape outside allowlist rejected

## Safe patch lifecycle

Capabilities: `code.patch`, `file.write` (approval required).

1. Backend builds patch payload (`files`, `unified_diff`, `project_root`, `summary`)
2. Policy validates every path (allowlisted extensions, no vendor dirs, no delete/rename)
3. `POST /api/v1/approvals` / chat creates approval with fingerprint
4. User approves in macOS **Approvals** UI
5. User clicks **Apply Approved Patch** (separate from approve)
6. `POST /api/v1/executions/apply-approved-patch` verifies fingerprint, consumes approval atomically, applies via temp-file replace
7. Audit: `patch.requested`, `patch.applied`, `patch.failed`, `patch.blocked`

Blocked: protected paths, binary, `.env`, lockfiles, `node_modules`, `.venv`, traversal, replay.

## Coding task workflow

Chat: `fix failing tests`, `propose patch`, `run validation`, `explain this error`.

Stages (timeline in chat + `coding_tasks` table):

1. Inspecting
2. Running tests
3. Analyzing failure
4. Patch proposed
5. Awaiting approval
6. Applying patch (after explicit apply)
7. Re-running validation
8. Completed / Failed

Model output is never trusted — all paths revalidated server-side.

## Worker dispatch

Worker commands (`apps/worker/commands.py`):

- `inspect_repo`
- `run_validation`
- `read_safe_file`
- `apply_approved_patch` (revalidates policy on worker)

Worker must belong to same user; dangerous tools remain disabled.

## Project memory

`project_memory` stores per user+device+project:

- last validation command/result
- last patch proposal
- last task summary
- recent task history (bounded)

## macOS UX

- Active project badge in Genie chat
- Task timeline strip during coding tasks
- Approvals: **Apply Approved Patch** for `code.patch` / `file.write`

## Manual demo

```bash
make start && make migrate
make dev          # API
make worker       # optional Mac worker
bash scripts/demo_useful_agent.sh
```

Manual smoke:

1. `set project ~/Projects/nova`
2. `current project`
3. `inspect repo`
4. `run validation`
5. Ask NOVA to explain an isolated demo failure
6. Approve patch in UI
7. **Apply Approved Patch**
8. Re-run validation
9. Confirm timeline + summary
10. Blocked: patch `~/NOVA_VAULT/test.txt`, `.env`, replay approval

## Startup commands

```bash
make bootstrap
make start
make migrate
make dev
# separate terminal:
make worker
# Ollama:
ollama serve && ollama pull qwen2.5:7b
```

## Security boundaries

| Enabled | Disabled |
|---------|----------|
| Safe shell (`make test`, `git status`, …) | Arbitrary shell |
| Patch inside active project | Git push |
| Read-only + approved write | Browser automation |
| Local Qwen proposals | n8n/OpenClaw |
| Explicit apply after approval | Auto-apply patches |

Protected file content is not sent to cloud providers (existing Phase 3D guards).

## Current limitations

- One active project per device
- No git commit/push in this milestone
- Patch proposals use heuristics + local model when available
- Worker dispatch for missions unchanged; project commands run locally or on worker WS
- No embeddings / vector memory

## Tests

```bash
make test   # includes tests/test_milestone_1_useful_agent.py
```
