# Milestone 3: Local Multi-Agent Orchestration

## Architecture

```
User → Chat / API → AgentPlanService → OrchestrationExecutor (allowlisted steps)
                              ↓
                    ApprovalRequestService (patch, branch, commit)
                              ↓
                    PatchExecutionService / GitWorkflowService (explicit apply only)
```

- **Bounded plans**: max 8 steps, max 2 retries per step
- **One active run per plan** (enforced via metadata `running` flag)
- **Ownership**: `user_id` + `device_id`
- **Default flow**: inspect → validate → propose patch → review → await approval → rerun validation → commit propose → final report

## Agent Roles

| Role | Responsibility |
|------|----------------|
| planner | Bounded step plan (deterministic template in M3) |
| inspector | Repo structure, README, git status, safe reads |
| coder | Minimal patch proposal (backend validates) |
| reviewer | Independent verdict: approved_for_user_review / needs_revision / blocked |
| validator | Allowlisted validation, bounded output |
| reporter | Final summary, commit proposal |

## Step Lifecycle

`pending` → `running` → `completed` | `failed` | `blocked` | `waiting_approval`

Safe action types only — see `nova_core/orchestration/step_types.py`.

## Trust Lanes

See [PROVIDER_TRUST_LANES.md](./PROVIDER_TRUST_LANES.md).

## Approval Boundaries

| Action | Approval |
|--------|----------|
| Patch apply | `code.patch` — approve then **Apply Approved Patch** |
| Branch create | `git.branch.create` — separate approval |
| Git commit | `git.commit` — separate approval |
| Git push | **Permanently blocked** |

Fingerprints bind exact payload (branch name, staged paths, commit message, patch files).

## Local Git Workflow

Allowed: status, diff --stat, propose branch, create branch (approved), propose commit, commit (approved).

Blocked: push, reset --hard, clean, checkout --, force, remote mutation.

## Background Integration

On validation failure from `repo.run_validation` / `repo.health_check`:

1. Creates **draft** orchestration plan only
2. Notification: "Validation failed. Draft repair plan ready."
3. Never auto-applies patch, never auto-commits, never uses external providers silently

## Chat Commands

- `create coding plan`
- `fix failing tests`
- `inspect this repo and propose a patch`
- `show active plan` / `show plan steps`
- `cancel plan` / `retry failed step`
- `which provider lane is active?`
- `propose commit` / `create approved branch` / `commit approved changes`

## Demo

```bash
make migrate
# start API + Ollama with qwen2.5:7b
chmod +x scripts/demo_agent_orchestration.sh
./scripts/demo_agent_orchestration.sh
```

## Startup

```bash
make migrate
make dev-api          # or your local API start
NOVA_EXTERNAL_PROVIDERS_ENABLED=false make test
```

## Limitations

- External provider adapters are scaffolds only (no paid calls in tests)
- No embeddings / vector project memory yet
- Planner uses deterministic template (not free-form LLM plan in M3)
- No browser, n8n, OpenClaw, or recursive self-modification
- Push permanently disabled

## macOS UX

Settings → **Orchestration** tab: plan timeline, patch review, commit proposal (Push Disabled), provider trust.
