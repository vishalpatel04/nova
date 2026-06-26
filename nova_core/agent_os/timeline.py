"""Mission timeline helpers."""

from __future__ import annotations

from typing import Any

from nova_core.agent_os.models import AgentMission, TimelineEvent, utc_now_iso


def append_timeline(
    mission: AgentMission,
    *,
    agent_id: str,
    display_name: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    mission.timeline_events.append(
        TimelineEvent(
            agent_id=agent_id,
            display_name=display_name,
            message=message,
            timestamp=utc_now_iso(),
            evidence=evidence or {},
        )
    )
    mission.updated_at = utc_now_iso()


def format_timeline_cli(mission: AgentMission) -> str:
    lines = ["NOVA Agent OS", f"Mission: {mission.user_request}", ""]
    for event in mission.timeline_events:
        lines.append(f"[{event.display_name}] {event.message}")
    return "\n".join(lines)


def format_final_report_cli(mission: AgentMission) -> str:
    report = mission.final_report
    lines = [
        "",
        "Final:",
        f"- Path: {report.get('path', mission.workspace_path)}",
        f"- Build: {report.get('build_status', 'UNKNOWN')}",
        f"- Preview: {report.get('preview_url', mission.preview_url or 'n/a')}",
        f"- Deployment: {report.get('deployment_status', 'unknown')}",
        f"- Evidence log: {report.get('evidence_log', mission.evidence_log_path or 'n/a')}",
    ]
    return "\n".join(lines)
