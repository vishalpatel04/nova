# External Agent Stack Audit

Audited clones under `external/` (gitignored — never commit into NOVA).

| Repo | Purpose | License | Integration |
|------|---------|---------|-------------|
| OpenHands | Self-hosted coding agent control center | MIT (OpenHands) | **Adapter** — `nova_core/forge/engines/openhands.py` |
| LangGraph | Stateful agent orchestration graphs | MIT (LangChain) | **Optional adapter** — internal MissionGraph default |
| OpenClaw | Personal assistant gateway/channels/skills | MIT (+ enterprise split) | **Reference only** — NOVA Gateway pattern |
| openWakeWord | Local wake-word detection | Apache-2.0 | **Optional adapter** — phrase fallback default |

---

## OpenHands (`external/openhands`)

**Purpose:** Run coding agents (OpenHands, Claude Code, Codex, etc.) across local/remote backends.

**Install:** Node/npm or Docker per upstream docs — not bundled in NOVA.

**Runtime:** Server URL or CLI subprocess.

**NOVA path:** Forge engine adapter via `NOVA_OPENHANDS_URL` or `NOVA_OPENHANDS_CMD`.

**Security:**
- Workspace-only execution
- No auto Docker pull
- Sentry before deploy/git push
- Secrets redacted in evidence prompts

**Do not:** Vendor OpenHands source, auto-install containers, pass vault paths.

**Docs:** [OPENHANDS_INTEGRATION.md](./OPENHANDS_INTEGRATION.md)

---

## LangGraph (`external/langgraph`)

**Purpose:** Graph-based multi-step agent workflows with checkpointing.

**Install:** `pip install langgraph` (optional).

**Runtime:** Python library; optional LangGraph Platform for production.

**NOVA path:** `MissionGraphRunner` (internal) + `LangGraphAdapter` when installed.

**Security:** Graph nodes are deterministic NOVA code; LLM calls stay in existing provider lanes.

**Do not:** Require LangGraph for investor demo; import entire langgraph monolith into hot path.

---

## OpenClaw (`external/openclaw`)

**Purpose:** Multi-channel personal assistant (Telegram, WhatsApp, skills/plugins).

**Install:** Upstream OpenClaw setup — reference only.

**Runtime:** Gateway daemon + channel connectors + skill registry (ClawHub).

**NOVA path:** `nova_core/gateway/*` mirrors channel envelope pattern. **Skills are NOT executed.**

**Security (critical):**
- Untrusted OpenClaw/ClawHub skills can exfiltrate data or run malicious code
- NOVA requires Sentry review + allowlisted skills only
- NOVA never auto-installs ClawHub plugins

**Do not:** Execute OpenClaw skills, proxy unreviewed plugin code, merge OpenClaw runtime into NOVA process.

**Docs:** [OPENCLAW_INTEGRATION.md](./OPENCLAW_INTEGRATION.md)

---

## openWakeWord (`external/openWakeWord`)

**Purpose:** Open-source wake-word models for voice interfaces.

**Install:** `pip install openwakeword` (+ optional custom "hey nova" model training).

**Runtime:** On-device audio inference; CPU-friendly.

**NOVA path:** `nova_core/voice/openwakeword_adapter.py` with transcript phrase fallback.

**Security:** Local-only audio; no cloud upload by default.

**Do not:** Block investor demo on model download; require mic in CI.

**Docs:** [WAKE_WORD_SETUP.md](./WAKE_WORD_SETUP.md), [VOICE_MODE.md](./VOICE_MODE.md)

---

## Summary recommendation

| System | Use as |
|--------|--------|
| LangGraph | Optional dependency OR inspiration for MissionGraph |
| OpenHands | Subprocess/API Forge engine |
| OpenClaw | Gateway/channel reference; skills blocked |
| openWakeWord | Optional wake-word backend |
| Qwen/Ollama | Private reasoning lane (existing) |
| Sentry | Approval gate (existing) |

Investor demo **must work offline** with deterministic Forge templates when external engines are unavailable.
