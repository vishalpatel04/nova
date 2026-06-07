# NOVA Provider Trust Lanes

## Overview

NOVA separates **local** inference from **external restricted** providers. Backend policy is authoritative; model output is advisory only.

## Local Lane (default)

- Providers: Ollama, Qwen, DeepSeek (local endpoints)
- May receive normal non-protected project content
- Protected paths (`NOVA_VAULT`, `.env`, keys, SSH, credentials) remain blocked
- Default model: `qwen2.5:7b` via Ollama

## External Restricted Lane

- Providers: Anthropic, OpenAI, Codex CLI (scaffold adapters)
- **Disabled by default** — requires explicit configuration:

```bash
NOVA_EXTERNAL_PROVIDERS_ENABLED=false   # default
NOVA_ANTHROPIC_ENABLED=false            # default
NOVA_OPENAI_ENABLED=false               # default
NOVA_CODEX_CLI_ENABLED=false            # default
```

- No external call unless flag enabled **and** per-request approval where required
- File content transmission requires `cloud.send_file` approval
- Never send protected content externally
- Never log prompt bodies containing sensitive data
- Runtime status exposes `configured=true/false` only — **no raw keys** in logs, API, UI, audit, or SSE

## Secret Storage

| Secret | Recommended storage |
|--------|---------------------|
| Provider API keys | macOS Keychain (`com.nova.macos.providers`) |
| NOVA vault files | `~/NOVA_VAULT` (protected path) |
| Device tokens | macOS Keychain per device |

Rules:

- Backend may retrieve API keys internally for adapter calls
- Chat agents **never** read raw keys
- File tools **never** read `NOVA_VAULT`
- Shell tools **never** dump environment
- External adapters receive only the key needed internally
- Keys **never** appear in prompts

## API

`GET /api/v1/provider-trust` — active lane and provider configured/enabled status (no key values).

Chat: `which provider lane is active?`
