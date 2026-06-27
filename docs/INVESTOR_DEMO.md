# NOVA Investor Demo Checklist

Premium Agent OS demo inside NOVAGenie chat — NOVA orchestrates local Qwen reasoning, MissionGraph evidence, Forge engines (template fallback), and Gmail draft with approval gates.

**Pitch:** NOVA does not replace Claude Code or OpenHands — it orchestrates them with memory, UI, Sentry approvals, and evidence.

## 1. Start services

```bash
cd ~/Projects/nova
make db-target
make migrate
make api
```

Optional demo pacing (reveals timeline steps gradually — real build still runs):

```bash
export NOVA_DEMO_PACING=true
```

Open **NOVAGenie** (920×760 default window; **War Room** mode uses 1000×760 minimum).

## War Room Demo

1. Open NOVAGenie and select **War Room** in the header toggle (default for investor demo).
2. Ask: `build a landing page for SusCo` — agents report in the group chat (Prime, Archive, Forge, QA, Sentry).
3. Open **Preview** from the right MissionGraph / Evidence panel.
4. Ask: `@Orbit draft an investor email about this app` — Orbit reports draft status in chat.
5. Ask: `@Sentry what needs approval?` — Sentry summarizes deploy/send gates.
6. Ask: `build a proper expense tracker with login and database` — NOVA offers Forge engines (Codex / Cursor / OpenHands).
7. Use Codex only if live limits allow; otherwise reply `use deterministic fallback`.

```bash
bash scripts/demo_war_room_payload.sh
```

## 2. Landing page with clarification

Type:

```
build a landing page for SusCo
```

NOVA shows a **Quick spec** plus 2–3 questions. Reply:

```
use your best assumptions
```

NOVA responds **Building with assumptions…** and shows the Agent OS mission card.

## 3. Preview and deploy gate

1. Click **Open Preview** — SusCo-branded landing page.
2. Click **No** on deploy approval.
3. Card updates to **Deployment skipped**.

## 4. Orbit email draft

Type:

```
draft an investor update email about this app
```

NOVA shows an **Orbit Email Draft** card:

- To / Subject / Body preview
- Draft source: local artifact (Gmail not configured) or Gmail when enabled
- **Send this email?** with **Yes** / **No**

Click **No** — send skipped honestly (no fake Gmail send).

## 5. Safety talking points

- App-build intents route **before** Qwen — deterministic templates.
- Vague requests get spec clarification; specific requests build directly.
- Deploy/package and email **send** require explicit approval.
- Gmail send integration is prepared but not auto-enabled in this build.

## 6. Fallback CLI

```bash
scripts/nova mission "build a landing page for SusCo"
scripts/nova timeline <mission_id>
bash scripts/demo_investor_end_to_end.sh
```

## 7. Automated demos

```bash
bash scripts/demo_investor_end_to_end.sh
bash scripts/demo_novagenie_chat_agent_os.sh
bash scripts/demo_agent_os_calculator.sh
bash scripts/demo_war_room_payload.sh
```

## WhatsApp (future)

WhatsApp support is planned via desktop automation with manual-send approval. For investor demos, **Gmail is primary** — API-based drafts, auditable evidence, and read-back.
