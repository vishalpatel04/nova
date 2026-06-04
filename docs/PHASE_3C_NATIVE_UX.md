# Phase 3C — Native Assistant UX

Phase 3C transforms NOVAGenie from a backend-capable runtime into a polished,
interactive native assistant while preserving Phase 3B security boundaries.

## Workstreams

### 1. Real streaming chat
- `POST /api/v1/chat/stream` — SSE token stream with session/done/cancelled events
- `POST /api/v1/chat/stream/{stream_id}/cancel` — cooperative cancellation
- `ProviderRuntime.stream()` — Ollama NDJSON streaming with fallback to word-chunk infer
- macOS `ChatStreamClient` — incremental rendering with non-streaming fallback

### 2. Voice loop foundation
- `VoiceRuntime` — push-to-talk orchestration (no wake word)
- `AVFoundationVoiceAdapter` — macOS STT/TTS via Speech + AVSpeechSynthesizer
- Visible recording state, cancel, playback interruption

### 3. Companion device UX
- `companion_inbox_items` table — device-scoped prompt queue
- `GET /api/v1/companion/inbox` — validated device ownership
- `POST /api/v1/companion/inbox/{id}/delivered|read` — delivery lifecycle
- iOS/macOS inbox UI foundation

### 4. Session restore
- `GET /api/v1/chat/sessions/latest` — backend restore
- macOS merges local SQLite snapshot with backend on launch

### 5. Native macOS polish
- Provider/streaming status indicators
- Cancel during stream
- Session list foundation
- Keyboard navigation preserved

### 6. Scheduler foundation (safe)
- `GET /api/v1/scheduler/status` — paused task visibility
- `POST /api/v1/scheduler/tick` — audit-only dispatcher (no execution)

## Security preserved
- Approval-gated automation unchanged
- n8n/OpenClaw real execution still blocked
- Companion target validation + revoked device rejection
- `blocked=true` semantics and audit logging unchanged
