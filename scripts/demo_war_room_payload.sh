#!/usr/bin/env bash
# War Room payload demo — agent reports, graph nodes, Forge/QA/Sentry fields.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== NOVA War Room Payload Demo =="

.venv/bin/pytest tests/test_war_room_payload.py -q

.venv/bin/python <<'PY'
from nova_core.agent_os.agent_reports import build_agent_reports
from nova_core.agent_os.chat_payload import build_agent_os_chat_payload
from nova_core.agent_os.models import AgentMission, MissionStatus, TimelineEvent

now = "2026-06-03T00:00:00Z"
mission = AgentMission(
    mission_id="demo-war-room",
    user_request="build a landing page for SusCo",
    mission_type="app_build",
    commander="Forge",
    squad=["forge"],
    status=MissionStatus.WAITING_APPROVAL,
    risk_level="medium",
    acceptance_criteria=["build passes"],
    timeline_events=[
        TimelineEvent(agent_id="prime", display_name="Prime", message="Classified app-build mission", timestamp=now),
        TimelineEvent(agent_id="archive", display_name="Archive", message="Context retrieved", timestamp=now),
        TimelineEvent(agent_id="forge", display_name="Forge", message="Selected codex_cli engine", timestamp=now),
        TimelineEvent(agent_id="qa_engineer", display_name="QA Engineer", message="Validation passed", timestamp=now),
        TimelineEvent(agent_id="sentry", display_name="Sentry", message="Deployment blocked until approval", timestamp=now),
    ],
    skill_calls=[],
    files_touched=[],
    commands_run=[],
    validation_results=[],
    approvals_required=["deploy"],
    final_report={
        "app_name": "SusCo",
        "build_status": "PASS",
        "preview_url": "http://127.0.0.1:5173",
        "forge_engine": "codex_cli",
    },
    artifacts={
        "mission_graph": {
            "nodes": [
                {"node_id": f"n{i}", "display_name": f"Node {i}", "status": "done", "output_summary": "ok"}
                for i in range(11)
            ]
        }
    },
    created_at=now,
    updated_at=now,
    preview_url="http://127.0.0.1:5173",
)
payload = build_agent_os_chat_payload(mission)
assert payload.get("agent_reports"), "missing agent_reports"
assert payload.get("war_room_roster"), "missing war_room_roster"
assert payload.get("agent_inspectors"), "missing agent_inspectors"
assert payload.get("agent_work_feed"), "missing agent_work_feed"
assert len(payload.get("graph_nodes") or []) >= 11, "missing mission_graph_nodes"
assert payload.get("voice_status"), "missing voice_status"
assert "push-to-talk" in payload["voice_status"]["fallback_message"].lower()
agents = {r["agent_id"] for r in payload["agent_reports"]}
for required in ("prime", "forge", "qa_engineer", "sentry"):
    assert required in agents, f"missing report for {required}"
inspectors = {r["agent_id"]: r for r in payload["agent_inspectors"]}
for required in ("prime", "forge", "qa_engineer", "sentry"):
    assert required in inspectors, f"missing inspector for {required}"
    assert inspectors[required]["what_doing"], f"missing work notes for {required}"
assert [n["display_name"] for n in payload["graph_nodes"][:11]] == [
    "Classify",
    "Retrieve",
    "Clarify",
    "Select Commander",
    "Select Engine",
    "Plan",
    "Execute",
    "Validate",
    "Review",
    "Sentry",
    "Final Report",
]
print("payload keys:", sorted(payload.keys()))
print("agent report count:", len(payload["agent_reports"]))
print("graph node count:", len(payload["graph_nodes"]))
print("agent inspector count:", len(payload["agent_inspectors"]))
print("voice:", payload["voice_status"]["fallback_message"])
PY

# Swift Codable sanity (optional when macOS sources present)
if [[ -f apps/macos/NOVA/Models/AgentOSMissionPayload.swift ]]; then
  echo "Swift War Room models present (decode verified in xcodebuild when run)"
fi

echo "DEMO: PASS"
