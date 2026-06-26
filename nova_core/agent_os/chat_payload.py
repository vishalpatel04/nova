"""Structured Agent OS payloads for chat and NOVAGenie UI."""

from __future__ import annotations

from typing import Any

from nova_core.agent_os.models import AgentMission, MissionStatus


def _timeline_status(event_index: int, total: int, message: str) -> str:
    lowered = message.lower()
    if "fail" in lowered or "blocked" in lowered:
        return "failed"
    if event_index < total - 1:
        return "done"
    if "approval" in lowered or "requires" in lowered:
        return "warning"
    return "done"


def _approval_kind(mission: AgentMission) -> str:
    runtime = mission.artifacts.get("runtime") or mission.final_report.get("runtime", "web")
    return "package" if runtime == "cli" else "deploy"


def _approval_question(mission: AgentMission) -> str:
    if mission.status != MissionStatus.WAITING_APPROVAL:
        return ""
    return "Package this app?" if _approval_kind(mission) == "package" else "Deploy this app?"


def _short_text(mission: AgentMission) -> str:
    report = mission.final_report
    if report.get("summary") and not report.get("path"):
        return str(report["summary"])
    app_name = report.get("app_name", mission.artifacts.get("app_name", "App"))
    build = report.get("build_status", "UNKNOWN")
    if mission.status == MissionStatus.WAITING_APPROVAL:
        question = _approval_question(mission)
        return f"Agent OS mission complete for {app_name}. Build: {build}. {question}"
    if report.get("deployment_status") == "skipped":
        kind = "Packaging" if _approval_kind(mission) == "package" else "Deployment"
        return f"{kind} skipped for {app_name}."
    if "approved" in str(report.get("deployment_status", "")).lower():
        return (
            f"Approval recorded for {app_name}. "
            "External deploy integration is prepared but not enabled in this build."
        )
    return f"Agent OS mission for {app_name}. Build: {build}."


def build_agent_os_chat_payload(mission: AgentMission) -> dict[str, Any]:
    report = mission.final_report
    runtime = mission.artifacts.get("runtime") or report.get("runtime", "web")
    timeline_events = mission.timeline_events
    agent_timeline = [
        {
            "agent": event.display_name,
            "agent_id": event.agent_id,
            "status": _timeline_status(index, len(timeline_events), event.message),
            "summary": event.message,
            "timestamp": event.timestamp,
        }
        for index, event in enumerate(timeline_events)
    ]
    approval_kind = _approval_kind(mission)
    approval_question = _approval_question(mission)
    actions: list[dict[str, Any]] = []
    if mission.status == MissionStatus.WAITING_APPROVAL:
        actions.extend(
            [
                {
                    "label": "Yes",
                    "action": "approve_mission",
                    "mission_id": mission.mission_id,
                },
                {
                    "label": "No",
                    "action": "skip_mission",
                    "mission_id": mission.mission_id,
                },
            ]
        )
    preview_url = mission.preview_url or report.get("preview_url")
    if preview_url:
        actions.append(
            {
                "label": "Open Preview",
                "action": "open_url",
                "url": preview_url,
            }
        )
    path = report.get("path", mission.workspace_path)
    if path:
        actions.append(
            {
                "label": "Copy Path",
                "action": "copy_text",
                "text": path,
            }
        )
    evidence = report.get("evidence_log", mission.evidence_log_path)
    if evidence:
        actions.append(
            {
                "label": "Evidence Log",
                "action": "copy_text",
                "text": evidence,
            }
        )

    return {
        "type": "agent_os_mission",
        "mission_id": mission.mission_id,
        "status": mission.status.value,
        "mission_title": mission.user_request,
        "agent_timeline": agent_timeline,
        "result": {
            "app_name": report.get("app_name", mission.artifacts.get("app_name")),
            "app_type": report.get("app_type", mission.artifacts.get("app_type")),
            "path": path,
            "build_status": report.get("build_status", "UNKNOWN"),
            "preview_url": preview_url,
            "run_command": report.get("run_command"),
            "evidence_log": evidence,
            "approval_kind": approval_kind,
            "approval_question": approval_question,
            "runtime": runtime,
            "deployment_status": report.get("deployment_status"),
        },
        "actions": actions,
        "text": _short_text(mission),
    }
