# Phase 3B Runtime

Phase 3B upgrades NOVAGenie from command chat into a local-first assistant runtime.

## Runtime Guarantees

- Pairing and device-token auth remain required for `/api/v1/chat` and runtime endpoints.
- Local/free providers are preferred by default.
- OpenAI and Anthropic calls are disabled unless `NOVA_PAID_PROVIDERS_ENABLED=true`.
- Dangerous automation is blocked unless an approved `approval_id` is supplied.
- Automation attempts are persisted in `automation_runs` and audited.
- Chat sessions and message history are persisted server-side and restored through `/api/v1/chat/sessions`.
- macOS also keeps an active local chat snapshot in `Application Support/NOVA/NOVAChat.sqlite`.

## Provider Runtime

The provider runtime supports:

- Ollama/local (`NOVA_OLLAMA_BASE_URL`)
- Qwen via Ollama-compatible endpoint (`NOVA_QWEN_BASE_URL`)
- DeepSeek via Ollama-compatible endpoint (`NOVA_DEEPSEEK_BASE_URL`)
- OpenAI when explicitly enabled and configured
- Anthropic when explicitly enabled and configured

`GET /api/v1/runtime/status` returns provider health, paid-provider state, and local-first status.

## Automation Runtime

`POST /api/v1/automation/execute` supports n8n, OpenClaw, and Shortcuts boundaries.

Safe inspection and dry-runs can complete without approval. Real execution remains blocked in
Phase 3B even when an approval record is supplied; n8n/OpenClaw webhooks are not invoked yet.

`POST /api/v1/automation/schedules` creates paused scheduled tasks. Scheduling is persisted, but
automatic firing is intentionally not enabled until a scheduler worker approval model is added.

## Code Assistance

Chat commands:

- `repo analysis`
- `explain code <path>`
- `generate patch <instruction>`

Repo analysis and explain use safe read-only allowlisted paths. Patch generation currently returns an
approval-required plan and is audited; it does not execute commands.

## Companion Foundation

`POST /api/v1/companion/prompts` queues a paired-device prompt into a persisted chat session. This is
the push-ready abstraction for the iPhone companion; actual push delivery is not enabled in this
phase.
