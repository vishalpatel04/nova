"""Convert mission timeline events into War Room agent reports."""

from __future__ import annotations

from typing import Any

_REPORT_PREFIXES: dict[str, str] = {
    "prime": "Prime",
    "forge": "Forge",
    "archive": "Archive",
    "sentry": "Sentry",
    "orbit": "Orbit",
    "muse": "Muse",
    "qa_engineer": "QA",
    "fixer": "Fixer",
    "devops_deploy": "Deploy",
    "product_planner": "Product Planner",
    "architect": "Architect",
    "frontend_engineer": "Engineer",
    "code_reviewer": "Code Reviewer",
}


def _friendly_report(agent_id: str, display_name: str, message: str) -> str:
    lowered = message.lower()
    if agent_id == "prime" and "classified" in lowered:
        return "I classified this mission and opened a MissionGraph run."
    if agent_id == "archive":
        return "I checked recent context and workspace policy."
    if agent_id == "forge" and "engine" in lowered:
        return message
    if agent_id == "forge":
        return "Engineering squad activated for this mission."
    if agent_id == "qa_engineer" and "validation" in lowered:
        return message.replace("npm run build", "Validation")
    if agent_id == "qa_engineer":
        return message
    if agent_id == "sentry" and "approval" in lowered:
        return "Deployment is blocked until you approve."
    if agent_id == "sentry":
        return message
    if agent_id == "devops_deploy" and "preview" in lowered:
        return message
    return message


def build_agent_reports(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for entry in timeline:
        agent_id = str(entry.get("agent_id") or entry.get("agent", "")).lower().replace(" ", "_")
        display = str(entry.get("agent") or _REPORT_PREFIXES.get(agent_id, "Agent"))
        summary = str(entry.get("summary") or "")
        reports.append(
            {
                "agent": display,
                "agent_id": agent_id or display.lower(),
                "status": entry.get("status", "done"),
                "report": _friendly_report(agent_id, display, summary),
                "timestamp": entry.get("timestamp"),
            }
        )
    return reports


def build_war_room_roster(
    timeline: list[dict[str, Any]],
    *,
    forge_engine: str = "",
    mission_status: str = "",
) -> list[dict[str, Any]]:
    roster_ids = [
        ("prime", "Prime", "star.fill", "nova_blue"),
        ("archive", "Archive", "books.vertical.fill", "mercury_silver"),
        ("forge", "Forge", "hammer.fill", "mars_red"),
        ("qa_engineer", "QA", "checkmark.seal.fill", "neptune_teal"),
        ("sentry", "Sentry", "shield.fill", "saturn_gold"),
        ("orbit", "Orbit", "envelope.fill", "venus_rose"),
        ("muse", "Muse", "paintbrush.fill", "jupiter_amber"),
        ("nexus", "Nexus", "point.3.connected.trianglepath.dotted", "nova_blue"),
    ]
    latest: dict[str, dict[str, Any]] = {}
    for entry in timeline:
        aid = str(entry.get("agent_id") or "").lower()
        if aid:
            latest[aid] = entry

    def _status(agent_id: str) -> str:
        entry = latest.get(agent_id)
        if not entry:
            return "idle"
        st = str(entry.get("status", "done"))
        msg = str(entry.get("summary", "")).lower()
        if "approval" in msg or "blocked" in msg:
            return "needs_approval"
        if st == "failed":
            return "blocked"
        if st == "warning":
            return "needs_approval"
        if agent_id == "forge" and forge_engine:
            return "working"
        if mission_status == "running" and agent_id == "prime":
            return "working"
        return "done" if st == "done" else "working"

    rows: list[dict[str, Any]] = []
    for agent_id, name, glyph, color in roster_ids:
        latest_entry = latest.get(agent_id)
        summary = str(latest_entry.get("summary", "")) if latest_entry else ""
        if agent_id == "forge" and forge_engine:
            summary = summary or f"Engine: {forge_engine.replace('_', ' ')}"
        rows.append(
            {
                "agent_id": agent_id,
                "display_name": name,
                "glyph": glyph,
                "color_token": color,
                "status": _status(agent_id),
                "task_summary": summary or "Standing by",
            }
        )
    if forge_engine:
        rows.append(
            {
                "agent_id": forge_engine,
                "display_name": forge_engine.replace("_", " ").title(),
                "glyph": "terminal.fill",
                "color_token": "mars_red",
                "status": (
                    "working" if mission_status in {"running", "waiting_approval"} else "done"
                ),
                "task_summary": f"Forge worker: {forge_engine}",
            }
        )
    return rows
