# Phase 3A — Interactive NOVAGenie + Safe Local Tools + Automation Foundation

Phase 3A adds interactive chat, a authenticated `/api/v1/chat` endpoint, safe read-only local tools, provider routing foundation, and automation scaffolds. **No dangerous write automation, shell execution, browser/desktop control, Gmail, or n8n execution.**

## Daily launch

```bash
export DEVICE_ID=arth-mac-client
bash scripts/run-novagenie-local.sh
```

Ensure API (`localhost:8000`), Postgres, Redis, and worker are running. On launch you should land in **authenticated chat**, not Pair Device.

## Chatting with NOVAGenie

- Type in the bottom input bar; **Enter** sends, **Shift+Enter** inserts a newline.
- Click **Send** or use the **mic** button for push-to-talk (permission prompt on first use).
- Messages persist for the app session; loading indicator shows while waiting for the API.

## Safe commands (via `POST /api/v1/chat`)

| Command | Description |
|---------|-------------|
| `system status` | Control plane + worker summary |
| `connected devices` | Paired devices |
| `worker status` | Online/stale/offline counts |
| `recent missions` | Last 10 missions |
| `create system status mission` | Queues a `system_status` mission |
| `list worker capabilities` | Worker capability report |
| `list directory [path]` | Allowlisted directory listing |
| `read file <path>` | Read allowlisted file (max 64KB) |
| `search <pattern> [in path]` | Regex search in allowlisted paths |
| `help` | Command list |

### Allowlisted paths

- `~/Projects/nova`
- `~/Desktop/NOVA-Safe-Test`

Blocked: `.env`, credentials, tokens, SSH keys, hidden secrets, writes/deletes/moves.

## Blocked commands

Requests like shell execution, file writes, email send, browser control, n8n/OpenClaw runs return:

> Blocked: this action requires approval/policy support and is not implemented yet.

Blocked actions create **audit events** (`chat.action_blocked`).

## Provider keys (macOS only)

Stored in **Keychain** service `com.nova.macos.providers` — never in `.env`, source, plist, logs, or tests output.

Configure in **Settings → Providers**:

- Default provider (OpenAI, Anthropic, Qwen, DeepSeek, Local/Ollama)
- Model name
- Local endpoint (default `http://localhost:11434`)
- Prefer free/local for low-level tasks (default **ON**)

Phase 3A routes simple commands rule-based; paid model calls are stubbed unless explicitly configured.

## Automation foundation (not executed)

Planned providers registered only: **n8n**, **OpenClaw**, **Shortcuts**. All execution returns not-implemented / requires approval.

## Intentionally not implemented

- Shell execution
- File writes/deletes/moves outside policy
- Browser/desktop automation
- Gmail/email send
- n8n / OpenClaw / Shortcuts execution
- Wake word / always-listening
- Paid LLM calls without explicit provider key configuration

## Tests

```bash
make test
xcodebuild -project apps/macos/NOVAGenie.xcodeproj -scheme NOVAGenie test
```

See also `tests/test_chat.py`, `tests/test_safe_tools.py`, `tests/test_provider_router.py`, `tests/test_automation_scaffold.py`.
