# NOVA Daily Driver Runbook

Quick reference for running NOVA as a daily local-first assistant.

## 1. Start Ollama

```bash
# macOS: launch Ollama.app, or:
ollama serve
```

Verify:

```bash
curl http://localhost:11434/api/tags
```

## 2. Install / verify model

```bash
ollama pull qwen2.5:7b
ollama run qwen2.5:7b "Say hi in one line"
```

Optional `.env` override:

```bash
NOVA_OLLAMA_MODEL=qwen2.5:7b
```

## 3. Start Docker services

```bash
make start
docker compose -f infra/docker-compose.yml ps
```

## 4. Migrate database

```bash
make migrate
```

## 5. Start API

```bash
make dev
# or: .venv/bin/uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

Verify:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/readiness
```

## 6. Install / start worker (optional)

```bash
make install-worker
make worker-status
# or foreground: make worker
```

## 7. Launch NOVAGenie

```bash
cd apps/macos
xcodebuild -project NOVAGenie.xcodeproj -scheme NOVAGenie build
open ~/Library/Developer/Xcode/DerivedData/*/Build/Products/Debug/NOVAGenie.app
```

Or use `scripts/run-novagenie-local.sh`.

Pair device if needed (Settings → Pair device). Summon hotkey: **⌃⌥ Space**.

## 8. QA check

```bash
chmod +x scripts/qa_daily_driver.sh
NOVA_CLIENT_TOKEN=<paired-device-token> scripts/qa_daily_driver.sh
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| **Ollama not running** | Start Ollama.app or `ollama serve`; confirm `curl localhost:11434/api/tags` |
| **Model missing** | `ollama pull qwen2.5:7b`; UI shows: "Model qwen2.5:7b not installed…" |
| **`/chat` route 404** | API not running or wrong base URL; restart `make dev`; check NOVAGenie Settings API URL |
| **NSURLErrorDomain -1011** | Bad HTTP response — usually API down, wrong port, or auth failure; verify health + pairing token |
| **Keychain prompt** | Approve access for NOVA; token stored under `com.nova.macos` |
| **Stale API server** | Kill old uvicorn on port 8000; restart `make dev` after pulling latest code |
| **Port conflicts** | `lsof -i :8000`; change `NOVA_API_PORT` or stop conflicting process |
| **Bootstrap text every reply** | Model name mismatch — see Phase 3C fix; verify `qwen2.5:7b` in `ollama list` |
| **Protected file blocked** | Expected for `.env`, `~/.ssh`, `~/NOVA_VAULT` — see [SECURITY_MODEL.md](./SECURITY_MODEL.md) |

## Daily smoke checklist

- [ ] `hi` → natural local model reply
- [ ] `system status` → formatted status
- [ ] `connected devices` → device list
- [ ] `list directory ~/Projects/nova` → directory listing
- [ ] `read file ~/Projects/nova/README.md` → file preview
- [ ] `read file ~/Projects/nova/.env` → **blocked**
- [ ] `read file ~/.ssh/id_rsa` → **blocked**
- [ ] `run shell rm -rf /` → **blocked** with command preview
