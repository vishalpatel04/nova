"""Mission timeline helpers."""

from __future__ import annotations

import time
from typing import Any

from nova_core.agent_os.models import AgentMission, MissionStatus, TimelineEvent, utc_now_iso

_DEMO_PACE_SECONDS = 0.35


def _maybe_demo_pace() -> None:
    try:
        from nova_core.schemas.settings import get_settings

        if get_settings().nova_demo_pacing:
            time.sleep(_DEMO_PACE_SECONDS)
    except Exception:
        return


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
    _maybe_demo_pace()


def format_timeline_cli(mission: AgentMission) -> str:
    lines = ["NOVA Agent OS", f"Mission: {mission.user_request}", ""]
    for event in mission.timeline_events:
        lines.append(f"[{event.display_name}] {event.message}")
    return "\n".join(lines)


def format_final_report_cli(mission: AgentMission) -> str:
    report = mission.final_report
    if report.get("summary") and not report.get("path"):
        lines = [
            "",
            report["summary"],
            f"- Mission ID: {mission.mission_id}",
        ]
        if report.get("evidence_log"):
            lines.append(f"- Evidence log: {report['evidence_log']}")
        return "\n".join(lines)

    app_name = report.get("app_name", mission.artifacts.get("app_name", "App"))
    app_type = report.get("app_type", mission.artifacts.get("app_type", "unknown"))
    build_status = report.get("build_status", "UNKNOWN")
    runtime = report.get("runtime", mission.artifacts.get("runtime", "web"))
    preview = report.get("preview_url", mission.preview_url)
    if preview:
        preview_line = preview
    elif runtime == "cli":
        preview_line = "n/a (CLI app)"
    elif report.get("preview_status") == "FAILED":
        preview_line = "FAILED"
        log_path = report.get("preview_log_path")
        if log_path:
            preview_line = f"FAILED (see {log_path})"
    else:
        preview_line = "n/a"

    deploy_status = report.get("deployment_status", "unknown")
    lines = [
        "",
        "App ready.",
        "",
        f"- Mission ID: {mission.mission_id}",
        f"- App: {app_name}",
        f"- Type: {app_type}",
        f"- Path: {report.get('path', mission.workspace_path)}",
        f"- Build: {build_status}",
        f"- Preview: {preview_line}",
        f"- Evidence log: {report.get('evidence_log', mission.evidence_log_path or 'n/a')}",
        f"- Deployment: {deploy_status}",
    ]
    if report.get("run_command"):
        lines.insert(-1, f"- Run: {report['run_command']}")

    if mission.status == MissionStatus.WAITING_APPROVAL:
        question = "Package this app?" if runtime == "cli" else "Deploy this app?"
        lines.extend(
            [
                "",
                question,
                "Type:",
                "  yes",
                "or:",
                "  no",
            ]
        )
    elif deploy_status == "skipped":
        lines.append("")
        lines.append("Deployment skipped.")
    elif deploy_status.startswith("deployed") or deploy_status.startswith("prepared"):
        lines.append("")
        lines.append(f"Deployment status: {deploy_status}")

    return "\n".join(lines)
