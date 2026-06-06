# NOVA Security Model (Phase 3D)

## Trust boundaries

NOVA separates **local providers** from **cloud providers**:

| Class | Providers | File access |
|-------|-----------|-------------|
| Local | Ollama, Qwen, DeepSeek (via local endpoint) | Safe read-only tools on allowlisted paths; protected paths always blocked |
| Cloud | OpenAI, Anthropic | Never receives protected path contents; non-protected file content requires explicit approval |

Local inference does **not** require Anthropic or OpenAI API keys. Ollama runs on your machine (`http://localhost:11434` by default).

## Protected paths (always blocked)

These are blocked for **all** providers and tools:

- `~/NOVA_VAULT` — recommended secrets vault
- `~/.ssh`, `~/.aws`, `~/.config`
- Any `.env` file
- `*.pem`, `*.key`, `*.p12`
- `id_rsa`, `id_ed25519`

Blocked requests return `blocked=true`, a clean user message, and an audit event with `reason=protected_path_block`. Logs use sanitized path labels (basename only), never full secret contents.

## Where to store keys

| Secret | Recommended location |
|--------|---------------------|
| API keys (optional cloud) | macOS Keychain via NOVAGenie Settings, or server `.env` |
| Personal vault files | `~/NOVA_VAULT` (never readable by NOVA tools) |
| Device auth tokens | Keychain (`com.nova.macos` / `com.nova.ios`) |

Backend may read provider keys from environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) or macOS Keychain for client settings. **Chat and file tools never read key files from disk.**

## Runtime status

`GET /api/v1/runtime/status` reports:

- Provider configured/healthy flags
- Active local model badge (e.g. `local · qwen2.5:7b`)
- Ollama reachability and model readiness

It never returns API key values. Details resembling secrets are redacted.

## Shell and automation

- Shell execution remains **approval-gated**; unsafe commands are blocked with a preview of the requested command.
- n8n/OpenClaw real execution remains disabled (Phase 3B/3C boundary).
- Automation runs require explicit approval.

## What NOVA can access

**Allowed (local, allowlisted paths only):**

- `~/Projects/nova` and configured safe roots
- System status, devices, missions (via authenticated API)
- Read-only directory listing, file read (≤64KB), ripgrep search

**Never allowed:**

- Protected vault/credential paths (above)
- Unrestricted shell execution
- Write/delete/send email/browser automation without approval

## Starting NOVA safely

1. Copy `.env.example` → `.env`; set `NOVA_TOKEN_PEPPER` and pairing tokens for non-dev.
2. Store cloud keys only in `.env` or Keychain — not in chat-accessible files.
3. Keep secrets in `~/NOVA_VAULT`, outside allowlisted project roots.
4. Run `ollama serve` (or Ollama.app) before expecting local model responses.
5. Use `scripts/qa_daily_driver.sh` to verify health before daily use.

See also: [DAILY_DRIVER_RUNBOOK.md](./DAILY_DRIVER_RUNBOOK.md)
