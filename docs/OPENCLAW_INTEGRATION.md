# OpenClaw Integration (Reference Only)

OpenClaw is a **reference architecture** for multi-channel assistants. NOVA implements its own Gateway — it does **not** run OpenClaw skills.

## What NOVA adopts

- Channel abstraction (`macos_chat`, `cli`, `voice`, future messengers)
- Unified message envelope with session + approval context
- Personal-ops routing into Agent OS

## What NOVA does NOT do

- Execute ClawHub / OpenClaw plugins
- Auto-install third-party skills
- Proxy unreviewed shell commands from OpenClaw

## Security stance

Untrusted agent skills may:

- Read sensitive files
- Exfiltrate tokens
- Run destructive commands

NOVA requires **Sentry review** and **allowlisted skills** only. See `GatewayRouter.openclaw_reference_only()`.

## Optional future connector

`NOVA_OPENCLAW_BASE_URL` may point to a read-only OpenClaw instance for channel mirroring — never for direct skill execution.

## Local study clone

```bash
git clone https://github.com/openclaw/openclaw external/openclaw
```

(`external/` is gitignored.)
