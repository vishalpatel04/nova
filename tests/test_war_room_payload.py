"""War Room payload and agent report tests."""

from __future__ import annotations

from nova_core.agent_os.agent_reports import build_agent_reports, build_war_room_roster
from nova_core.agent_os.chat_payload import build_agent_os_chat_payload
from nova_core.agent_os.models import AgentMission, MissionStatus, TimelineEvent
from nova_core.chat.mentions import parse_agent_mention, route_mention_intent


def test_parse_agent_mention_routes_forge() -> None:
    agent, body = parse_agent_mention("@Forge use codex to improve this app")
    assert agent == "forge"
    assert "codex" in body
    routed = route_mention_intent(agent, body)
    assert routed == ("agent_os_mission", {"request": body})


def test_parse_agent_mention_unknown_returns_none() -> None:
    agent, body = parse_agent_mention("@Unknown hello")
    assert agent is None
    assert body == "@Unknown hello"


def test_agent_reports_from_timeline() -> None:
    timeline = [
        {
            "agent": "Prime",
            "agent_id": "prime",
            "status": "done",
            "summary": "Classified as app-build mission",
        },
        {
            "agent": "Forge",
            "agent_id": "forge",
            "status": "done",
            "summary": "Selected codex_cli engine",
        },
    ]
    reports = build_agent_reports(timeline)
    assert len(reports) == 2
    assert reports[0]["agent"] == "Prime"
    assert "classified" in reports[0]["report"].lower()


def test_war_room_roster_includes_forge_worker() -> None:
    timeline = [
        {
            "agent_id": "forge",
            "agent": "Forge",
            "status": "done",
            "summary": "Engine selected",
        }
    ]
    roster = build_war_room_roster(timeline, forge_engine="codex_cli", mission_status="running")
    assert any(row["agent_id"] == "codex_cli" for row in roster)
    forge = next(row for row in roster if row["agent_id"] == "forge")
    assert forge["status"] in {"working", "done"}


def _sample_mission() -> AgentMission:
    now = "2026-06-03T00:00:00Z"
    return AgentMission(
        mission_id="m-war-room-1",
        user_request="build a landing page for SusCo",
        mission_type="app_build",
        commander="Forge",
        squad=["forge", "qa_engineer"],
        status=MissionStatus.WAITING_APPROVAL,
        risk_level="medium",
        acceptance_criteria=["build passes"],
        timeline_events=[
            TimelineEvent(
                agent_id="prime",
                display_name="Prime",
                message="Classified landing page mission",
                timestamp=now,
            ),
            TimelineEvent(
                agent_id="forge",
                display_name="Forge",
                message="Selected deterministic_template engine",
                timestamp=now,
            ),
            TimelineEvent(
                agent_id="qa_engineer",
                display_name="QA Engineer",
                message="Validation passed: npm run build",
                timestamp=now,
            ),
            TimelineEvent(
                agent_id="sentry",
                display_name="Sentry",
                message="Deployment requires approval",
                timestamp=now,
            ),
        ],
        skill_calls=[],
        files_touched=[],
        commands_run=[],
        validation_results=[],
        approvals_required=["deploy"],
        artifacts={
            "mission_graph": {
                "nodes": [
                    {
                        "node_id": "classify",
                        "display_name": "Classify",
                        "status": "done",
                        "output_summary": "landing_page",
                    }
                ]
            }
        },
        final_report={
            "app_name": "SusCo",
            "build_status": "PASS",
            "preview_url": "http://127.0.0.1:5173",
            "forge_engine": "deterministic_template",
        },
        created_at=now,
        updated_at=now,
        preview_url="http://127.0.0.1:5173",
    )


def test_chat_payload_includes_war_room_fields() -> None:
    payload = build_agent_os_chat_payload(_sample_mission())
    assert payload["agent_reports"]
    assert payload["war_room_roster"]
    assert payload["graph_nodes"]
    assert any("Forge" in r["agent"] or "forge" in r["agent_id"] for r in payload["agent_reports"])
    assert any("QA" in r["agent"] for r in payload["agent_reports"])
