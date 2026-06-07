# NOVA Daily Driver Chat, Memory, and Voice

Branch: `feat/daily-driver-chat-memory-voice`  
Commit: `0e6436534d0e67b5bf6eab29bc4a366c74ad825f`  
Migration head: `0013_daily_driver_memory_voice`

This document describes the daily-driver slice that makes the macOS compact popup the primary chat surface: real local conversational replies, bounded session memory, structured personal memory, safe personal search with multi-turn follow-ups, compact popup UX fixes, runtime/provider status, and popup-open wake-word voice input.

Related code: `apps/api/services/chat.py`, `apps/api/services/runtime.py`, `apps/macos/NOVA/MacAppState.swift`, `apps/macos/NOVA/Views/GenieChatView.swift`, `apps/macos/NOVA/Voice/VoiceRuntime.swift`, `scripts/demo_daily_driver.sh`.

---

## Overview

| Area | What changed |
|------|--------------|
| Chat routing | General messages call local Ollama/Qwen/DeepSeek with a bounded prompt built from recent turns, active project, and saved memory. Deterministic commands still win over the model. |
| Session memory | Backend `chat_sessions` / `chat_message_records` persist turns. The popup restores the latest local snapshot and can reload backend sessions. |
| Structured memory | New `user_memory` table (migration `0013`). `remember` / `forget` / list commands store user-approved facts per user. |
| Personal search | Scoped and broad natural-language search phrases route to read-only personal-folder search without requiring an active project. Pending folder-choice follow-ups are consumed before Ollama. |
| Compact popup UX | Header shows provider badge, project, pending search state; streaming responses collapse to final text; long answers use Show more; errors are dismissible. |
| Voice | On-device STT via AVFoundation; optional wake-word listening only while the popup is open; Voice Off kill switch. |

Paid providers remain opt-in. Personal search and voice do not send filesystem content or raw audio to cloud services.

---

## Root causes fixed

1. **Canned rule-based replies for general chat** — Arbitrary questions (for example `hi`, factual lookups) could return the static help stub instead of a local model response when Ollama was available.
2. **Lost search follow-ups** — After `search my computer for …`, replies such as `Downloads` were treated as general chat and sent to Ollama instead of executing scoped personal search.
3. **Scoped search requiring active project** — Phrases like `search Assignment in ~/Downloads` or `search Assignment In ~/Downloads` could incorrectly require an active project. Scoped personal search now parses case-insensitively and does not depend on project state.
4. **Stuck loading UI** — The compact popup could leave a permanent `Working` placeholder or partial stream tokens instead of the final assistant message.
5. **No conversation context in local prompts** — Recent turns were not included in the Ollama prompt, so multi-turn chat felt stateless.
6. **No durable personal preferences** — User facts (for example file locations) were not stored across sessions.
7. **Weak runtime visibility** — Provider badge and `/api/v1/runtime/status` did not clearly expose local availability, selected model, or degraded mode.

---

## Runtime / chat behavior

### Routing precedence

For each message, `ChatService` applies this order:

1. Capability / approval evaluation (unchanged)
2. Deterministic command handlers (`help`, `system status`, `remember`, `search …`, etc.)
3. Pending tool-intent resolution (`personal_search.scope_confirmation` follow-ups)
4. General local chat via `_general_chat_response` → `ProviderRuntime.infer`
5. Degraded fallback only when the provider layer reports unavailability (`degraded_rule_based` + `_default_help()`)

Explicit tool commands cancel any active pending search intent for the session before running.

### General local chat

- Prompt includes: system instructions, active project (if set), up to **8** structured memory lines, up to **16** recent user/assistant turns (excluding blocked turns and raw file/search tool output), and the current user message.
- Prompt is capped at **6000** characters; individual turn excerpts are capped at **320** characters.
- Response metadata includes `runtime_mode`, `selected_provider`, `selected_model`, `fallback_reason`, and `local_available`.
- Streaming (`POST /api/v1/chat/stream`) uses the same prompt; the macOS client replaces the streaming bubble with the final `done` payload text.

### Session lifecycle

- Sessions are created server-side on first message; clients pass `session_id` to continue a thread.
- **New Chat** (`MacAppState.startNewChat`) clears the active session id, local messages, draft, pending tool intent, and task timeline. Older backend sessions remain listed under Recent Chats.
- **Clear Current Conversation** calls the same reset as New Chat (local thread only; structured `user_memory` is not deleted).
- On launch, the popup loads a local SQLite snapshot, then refreshes runtime status and recent session summaries from the API.

---

## Memory behavior

### Conversation memory (session-scoped)

- Stored in `chat_message_records` linked to `chat_sessions`.
- Included in the local model prompt for the active session only.
- Cleared locally by New Chat / Clear Current Conversation; not deleted from the database unless separately implemented.

### Structured personal memory (user-scoped)

Migration `0013` adds `user_memory` with unique `(user_id, key)`.

| Command | Intent | Behavior |
|---------|--------|----------|
| `remember that …` / `remember …` | `remember_memory` | Parses key/value, upserts row, audits `user_memory.remembered` |
| `what do you remember about me?` | `memory_summary` | Lists saved keys and values |
| `forget <key>` / `forget that …` | `forget_memory` | Deletes by normalized key |
| `where are my … stored?` (and similar) | `memory_lookup` | Returns matching `value_summary` without calling the model |

**Rejection rules** (stored memory is blocked if key or value matches):

- Secret-like markers: `password`, `token`, `api key`, `sk-`, `ssh-rsa`, `credential`, etc.
- Environment-like values containing `=`

Structured memory survives New Chat and is injected into every general local prompt for that user.

---

## Personal search behavior

### Approved read-only roots

- `~/Desktop`, `~/Documents`, `~/Downloads`, `~/Projects`
- Project editing allowlists are unchanged; search roots are read-only scopes.

### Command forms

| Input | Behavior |
|-------|----------|
| `search <pattern>` | Active project only (requires set project) |
| `search <pattern> in ~/Downloads` (case-insensitive `in`) | Scoped personal search; no active project required |
| Natural scoped phrases (`search Downloads for assignment`, `find … in my Documents`, etc.) | Parsed by `_parse_scoped_personal_search` |
| `search all approved folders for <pattern>` | All four roots |
| `search my computer for <pattern>` / `find everything related to X on my Mac` | Creates pending folder-choice intent |
| Follow-up: `Downloads`, `Documents`, `Desktop`, `Projects`, `yes`, `all`, `all approved folders` | Executes scoped or all-approved search |
| Follow-up: `no`, `cancel` | Cancels pending intent |
| Unrelated follow-up while pending | Re-prompts; does not call Ollama |

Pending intents live in `pending_tool_intents` (migration `0012`), TTL **5 minutes**, one active pending intent per session, ownership enforced by `session_id` + `user_id` + `device_id`.

Protected paths (`~/NOVA_VAULT`, `~/.ssh`, `.env`, keys, etc.) remain blocked. Search is bounded, read-only, and local.

---

## Compact popup UX behavior

Implemented in `GenieChatView` + `MacAppState`:

- **Status bar**: provider health dot, `providerBadge`, active project name, pending tool intent chip, optional task timeline strip, degraded hint when Ollama is unavailable.
- **Header controls**: Recent Chats menu (restore session), New Chat, push-to-talk mic.
- **Messages**: streaming tokens update in place; `done` event replaces content with the final response (avoids leaving partial stream text).
- **Loading**: `NOVA is thinking…` progress row when sending without stream tokens; avoids indefinite `Working` after completion.
- **Long answers**: collapse at 700 characters with **Show more** / **Show less**.
- **Errors**: dismissible banner; blocked responses use error styling.
- **Quick suggestion chips**: horizontal scroll; do not overlay the message list.

Voice preferences are in Settings → Voice (see below).

---

## Voice and wake-word behavior

All speech processing is on-device via `AVFoundationVoiceAdapter` / `VoiceRuntime`. No cloud STT/TTS.

| Setting | Default | Behavior |
|---------|---------|----------|
| Enable microphone input | on | Allows push-to-talk |
| Enable "Hey Nova" while popup is open | off | Wake-word loop only when compact window is visible |
| Start listening when popup opens | off | Auto-start wake or PTT on open |
| Auto-send after voice transcription | off | Sends message after PTT completes |
| Sound cue on wake | off | Optional feedback when wake phrase detected |
| Stop listening when popup closes | on | Stops STT when popup dismisses |
| Voice Off kill switch | off | Immediately stops all voice activity |

**Wake phrases** (case-insensitive substring match on live transcript): `nova`, `hey nova`, `okay nova`.

**Phases**: `idle` → `wakeListening` → `recording` → `transcribing` → (optional) `speaking`.

Wake-word mode requires on-device speech recognition support; if unavailable, wake-word stays disabled (push-to-talk may still work after permission grant).

---

## Privacy and security guarantees

- **Local-first chat**: General prompts go to configured local providers before any paid route.
- **No secret storage**: Structured memory rejects credentials, tokens, and env-like values.
- **No cloud personal search**: Search results are formatted server-side from local filesystem reads within approved roots; protected paths are blocked before reads.
- **No cloud voice**: Audio is processed by macOS Speech framework; raw audio is not persisted by default.
- **Pending intents**: Store only search query and scope metadata, not file contents.
- **Audit events**: Memory remember/forget and blocked paths continue to emit audit records.
- **Popup-only wake word**: No background microphone use while the compact window is closed.

---

## Validation commands

Run from repository root unless noted.

```bash
make lint
make typecheck
make test
make migrate
.venv/bin/alembic current
.venv/bin/alembic heads
docker compose -f infra/docker-compose.yml config -q
```

macOS (from `apps/macos`):

```bash
xcodebuild -project NOVAGenie.xcodeproj -scheme NOVAGenie build
xcodebuild -project NOVAGenie.xcodeproj -scheme NOVAGenie test
```

iOS (from `apps/ios`):

```bash
xcodebuild -project NOVA.xcodeproj -scheme NOVA \
  -destination 'generic/platform=iOS Simulator' build
```

Daily-driver API demo (requires paired client token and running API + Ollama):

```bash
export NOVA_DEMO_TOKEN="<paired-client-token>"
bash scripts/demo_daily_driver.sh
```

Optional broader QA harness:

```bash
bash scripts/qa_daily_driver.sh
```

### Verified results (branch `feat/daily-driver-chat-memory-voice`, commit `0e643653`)

| Check | Result |
|-------|--------|
| `make lint` | PASS |
| `make typecheck` | PASS |
| `make test` | PASS — **318 passed** |
| `make migrate` | PASS |
| `.venv/bin/alembic current` | PASS — `0013_daily_driver_memory_voice` |
| `.venv/bin/alembic heads` | PASS — single head |
| `docker compose -f infra/docker-compose.yml config -q` | PASS |
| macOS build | PASS |
| macOS XCTest | PASS — **41 tests** |
| iOS generic simulator build | PASS |
| iPhone 17 Pro simulator test run | **Not run** — destination unavailable in CI/local environment |
| `bash scripts/demo_daily_driver.sh` | PASS |
| macOS GUI manual smoke | **Not run** during validation |

---

## Demo flow

`scripts/demo_daily_driver.sh` exercises the API path end-to-end (no GUI):

1. Verify API health and Ollama + qwen model tags
2. Verify paired client token against `/api/v1/runtime/status`
3. Send `hi` — expect non-degraded local response
4. Send arbitrary question — expect real model text, not canned help stub
5. Set active project under `~/Desktop/NOVA-Safe-Test/daily-driver-*` (restores previous project on exit)
6. Confirm runtime status payload includes provider badge
7. `search my computer for assignment` — expect folder-choice prompt + pending intent
8. Reply `Downloads` — expect scoped search results
9. Confirm response is not a stuck placeholder (`Working`, `…`)
10. Broad search natural phrase → folder-choice prompt
11. Reply `no` — expect `Search cancelled.` / `pending_cancelled`
12. Protected read `~/NOVA_VAULT/secret` — expect blocked
13. `remember that my exchange files are usually in Downloads`
14. `where are my exchange files usually stored?` — expect `Downloads`
15. `what do you remember about me?` — expect remembered fact
16. New session message — structured memory still present
17. Runtime status shows actual provider badge

Requires: `NOVA_DEMO_TOKEN`, API at `NOVA_API_URL` (default `http://localhost:8000`), Ollama with qwen model, allowlisted safe root.

---

## Known limitations

**Verified gaps (by design or not yet implemented):**

- Wake-word and microphone access only while the compact popup is open; no listening when NOVAGenie is fully closed.
- Background always-on wake word is not implemented (requires separate privacy review).
- `search <pattern>` without a scope still requires an active project.
- Conversation memory in the local prompt is bounded (16 turns / 6000 chars); very long threads truncate oldest context.
- Structured memory lookup uses deterministic key matching for `where are …` questions; paraphrases outside supported patterns fall through to general chat.
- iPhone 17 Pro simulator tests were not executed in validation (destination unavailable).
- macOS GUI smoke (popup layout, wake-word manual steps below) was not run as part of automated validation.

**Operational notes:**

- Degraded badge means Ollama is unreachable or the configured model is not installed (`ollama pull qwen2.5:7b`).
- If wake-word is unsupported on the device, use push-to-talk.
- Protected file access should return a clean blocked message with audit, not a stack trace.

---

## Manual GUI smoke (not automated)

1. Start Ollama; ensure `qwen2.5:7b` is pulled.
2. Start API; run migrations.
3. Launch NOVAGenie; pair or restore Keychain token.
4. Open compact popup; confirm provider badge and project name (if set).
5. Send `hi` — confirm conversational local reply.
6. `search my computer for lund` → reply `Downloads` — confirm search executes.
7. Settings → Voice: enable wake-word; reopen popup; say `Hey Nova`; confirm listening state; speak a request; confirm transcript in input.
8. Enable **Voice Off** — confirm recording stops immediately.

---

## Safe to Review / Merge

- Branch `feat/daily-driver-chat-memory-voice` at commit `0e6436534d0e67b5bf6eab29bc4a366c74ad825f` is **clean** (focused daily-driver slice).
- Automated validation listed above **passed** on this branch (318 Python tests, 41 macOS unit tests, demo script, migration head `0013`).
- **GUI manual smoke was not run** during validation; reviewers should spot-check the popup and wake-word flow locally if merging to main for daily use.

---

## Startup checklist

1. Start Ollama and pull the configured model (default `qwen2.5:7b`).
2. Start the API; run `make migrate`.
3. Launch NOVAGenie; pair or restore Keychain token.
4. Optional: `set project ~/Projects/nova` for project-scoped search and coding commands.

See also: [Daily Driver Runbook](DAILY_DRIVER_RUNBOOK.md), [Phase 3B Runtime](PHASE_3B_RUNTIME.md).
