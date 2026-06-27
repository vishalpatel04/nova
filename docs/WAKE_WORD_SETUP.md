# Wake Word Setup (openWakeWord)

## Default (no extra deps)

NOVA uses transcript phrase detection: `hey nova`, `okay nova`, `nova`.

Works in NOVAGenie (macOS Speech) and CLI simulation.

## Optional: openWakeWord

```bash
pip install openwakeword
nova voice setup-openwakeword
nova voice status
```

Train or map a custom "hey nova" model per upstream openWakeWord docs.

## CLI

```bash
nova voice --simulate "hey nova build a todo app called voice tasks"
nova voice status
nova voice --listen   # requires openWakeWord + mic
```

## High-risk voice approvals

Require explicit phrases:

- `yes, send email`
- `yes, approve deployment`
- `yes, push branch`

Casual `yes` after wake is insufficient for Level 2/3 actions.

## CI

Use `--simulate` only — no microphone required.

See also [VOICE_MODE.md](./VOICE_MODE.md).
