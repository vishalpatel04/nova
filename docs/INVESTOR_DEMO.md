# NOVA Investor Demo Checklist

This guide walks through the Agent OS investor demo inside the NOVA macOS app (NOVAGenie). The CLI remains available as a fallback.

## 1. Start services

```bash
cd ~/Projects/nova
make db-target
make migrate
make api   # or: docker compose up
```

Open **NOVAGenie** from Xcode or the built `.app`.

## 2. Open NOVA chat

Confirm the provider badge shows local/Ollama health. The chat panel uses a frosted glass command-centre style.

## 3. Build a landing page

Type:

```
build a landing page for SusCo
```

Expected:

- Agent timeline card: Prime → Archive → Forge → Product Planner → Architect → Frontend Engineer → QA → Code Reviewer → Deploy Engineer → Sentry
- Build status **PASS**
- **Open Preview** button with verified preview URL
- Approval: **Deploy this app?** with **Yes** / **No**

## 4. Preview and decline deploy

1. Click **Open Preview** — landing page opens in the browser.
2. Click **No** on deployment approval.
3. Card updates to **Deployment skipped**.

## 5. CLI calculator app

Type:

```
create a simple command-line calculator app named arth
```

Expected:

- Timeline card with CLI validation (py_compile + smoke test **PASS**)
- **Run** command shown (`python3 ...`)
- **Package this app?** with **Yes** / **No**
- No pasted Python script or “Save this as …” response

## 6. Safety gates (talking points)

- Agent OS app-build intents are routed **before** Qwen/Ollama — deterministic templates, no model required.
- Sentry requires explicit approval for deploy/package.
- External Vercel deploy is **not** auto-run in this build; **Yes** records approval honestly.
- High-risk shell/exec intents remain blocked.

## 7. Fallback CLI (if app UI fails)

```bash
scripts/nova mission "build a landing page for SusCo"
scripts/nova timeline <mission_id>
scripts/nova preview <mission_id>
scripts/nova deploy <mission_id>   # after approve
```

## 8. Automated demo scripts

```bash
bash scripts/demo_novagenie_chat_agent_os.sh
bash scripts/demo_agent_os_chat_app_routing.sh
bash scripts/demo_agent_os_calculator.sh
bash scripts/demo_agent_os_multi_app.sh
```

## Model lanes (optional)

```bash
scripts/nova models
NOVA_LOCAL_MODEL=qwen2.5:7b scripts/nova models
scripts/nova pull-model qwen2.5:7b   # explicit only
```

Agent OS app building does **not** depend on model availability.
