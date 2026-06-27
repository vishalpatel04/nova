# OpenHands Integration

NOVA delegates serious Forge coding tasks to OpenHands via an adapter — never vendors the repo.

## Configuration

```bash
# Option A: HTTP API
export NOVA_OPENHANDS_URL=http://127.0.0.1:3000

# Option B: local CLI
export NOVA_OPENHANDS_CMD="openhands run"
```

## CLI

```bash
nova forge engines
nova forge check
nova forge run "improve error handling" --project ~/Projects/nova-workspace/my-app --engine openhands
```

## Fallback

If OpenHands is unavailable, NOVA prints a setup hint and runs `deterministic_template`.

## Safety

- Workspace-only paths
- Prompt files written to `.nova-forge-evidence/` with redacted secrets
- No git push/deploy without Sentry approval
- No auto Docker image pulls

## Local study clone

```bash
git clone https://github.com/OpenHands/agent-canvas external/openhands
```

(`external/` is gitignored.)

## Demo

```bash
bash scripts/demo_openhands_adapter.sh
```
