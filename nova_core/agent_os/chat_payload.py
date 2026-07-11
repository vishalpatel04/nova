"""Structured Agent OS payloads for chat and NOVAGenie UI."""

from __future__ import annotations

from typing import Any

from nova_core.agent_os.agent_reports import build_agent_reports, build_war_room_roster
from nova_core.agent_os.models import AgentMission, MissionStatus
from nova_core.voice.openwakeword_adapter import status as openwakeword_status

_GRAPH_STEPS: tuple[tuple[str, str, str, str], ...] = (
    ("classify_request", "classify", "Classify", "prime"),
    ("retrieve_context", "retrieve", "Retrieve", "archive"),
    ("clarify_requirements", "clarify", "Clarify", "prime"),
    ("select_commander", "select_commander", "Select Commander", "prime"),
    ("select_engine", "select_engine", "Select Engine", "forge"),
    ("plan", "plan", "Plan", "nexus"),
    ("execute", "execute", "Execute", "forge"),
    ("validate", "validate", "Validate", "qa_engineer"),
    ("review", "review", "Review", "qa_engineer"),
    ("sentry_gate", "sentry", "Sentry", "sentry"),
    ("final_report", "final_report", "Final Report", "prime"),
)

_GRAPH_ALIASES: dict[str, str] = {
    canonical: canonical for canonical, _public_id, _name, _agent in _GRAPH_STEPS
}
_GRAPH_ALIASES.update(
    {public_id: canonical for canonical, public_id, _name, _agent in _GRAPH_STEPS}
)

_AGENT_ROLES: dict[str, str] = {
    "prime": "Mission commander",
    "archive": "Context and memory",
    "forge": "Builder / coding execution",
    "qa_engineer": "Validation",
    "qa": "Validation",
    "sentry": "Safety and approvals",
    "orbit": "Gmail / communications",
    "muse": "Copy, design, and presentation polish",
    "nexus": "Planning and strategy",
}

_AGENT_ASK_COMMANDS: dict[str, str] = {
    "prime": "@Prime summarize the mission",
    "archive": "@Archive find related files",
    "forge": "@Forge improve this app",
    "qa_engineer": "@QA validate the build",
    "qa": "@QA validate the build",
    "sentry": "@Sentry what needs approval?",
    "orbit": "@Orbit draft investor email",
    "muse": "@Muse make this more investor-ready",
    "nexus": "@Nexus plan next milestone",
}

_AGENT_NODE_MAP: dict[str, tuple[str, ...]] = {
    "prime": ("classify_request", "clarify_requirements", "select_commander", "final_report"),
    "archive": ("retrieve_context",),
    "forge": ("select_engine", "execute"),
    "qa_engineer": ("validate", "review"),
    "qa": ("validate", "review"),
    "sentry": ("sentry_gate",),
    "orbit": (),
    "muse": ("review",),
    "nexus": ("plan",),
}


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
    if report.get("demo_chat_summary"):
        return str(report["demo_chat_summary"])
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


def _normalize_graph_nodes(raw_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_canonical: dict[str, dict[str, Any]] = {}
    unknown_nodes: list[dict[str, Any]] = []
    for raw in raw_nodes:
        raw_id = str(raw.get("node_id", ""))
        canonical = _GRAPH_ALIASES.get(raw_id)
        if canonical is None:
            unknown_nodes.append(dict(raw))
            continue
        by_canonical[canonical] = dict(raw)

    normalized: list[dict[str, Any]] = []
    for canonical, public_id, display_name, agent_id in _GRAPH_STEPS:
        raw = by_canonical.get(canonical, {})
        normalized.append(
            {
                "node_id": canonical,
                "public_id": public_id,
                "display_name": display_name,
                "status": str(raw.get("status", "pending")),
                "output_summary": str(raw.get("output_summary", "")),
                "duration_ms": raw.get("duration_ms"),
                "selected_agent": agent_id,
                "evidence": list(raw.get("evidence") or []),
                "error": raw.get("error"),
            }
        )
    for raw in unknown_nodes:
        raw.setdefault("public_id", raw.get("node_id", "node"))
        raw.setdefault("selected_agent", "")
        raw.setdefault("evidence", [])
        normalized.append(raw)
    return normalized


def _last_by_agent(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        agent_id = str(row.get("agent_id") or "").lower()
        if agent_id:
            latest[agent_id] = row
    return latest


def _agent_role(agent_id: str) -> str:
    if agent_id in _AGENT_ROLES:
        return _AGENT_ROLES[agent_id]
    return "Selected Forge worker" if agent_id else "Agent"


def _agent_ask(agent_id: str, display_name: str) -> str:
    if agent_id in _AGENT_ASK_COMMANDS:
        return _AGENT_ASK_COMMANDS[agent_id]
    return f"@Forge ask {display_name} for current status"


def _what_doing(
    agent_id: str,
    *,
    task: str,
    report: str,
    mission: AgentMission,
    forge_engine: str,
) -> str:
    if agent_id == "prime":
        return "Classifying the request, coordinating MissionGraph, and preparing the final report."
    if agent_id == "archive":
        return "Checking local context, memory, and workspace policy for relevant background."
    if agent_id == "forge":
        engine = forge_engine.replace("_", " ") if forge_engine else "selected Forge engine"
        return f"Building with {engine}; tracking changed files and validation evidence."
    if agent_id in {"qa_engineer", "qa"}:
        build = str(mission.final_report.get("build_status", "UNKNOWN"))
        return f"Checking build and test status. Current build result: {build}."
    if agent_id == "sentry":
        if mission.status == MissionStatus.WAITING_APPROVAL:
            return "Holding the approval gate before deploy/package or external side effects."
        return "Monitoring approvals, risk, and blocked actions."
    if agent_id == "orbit":
        return "Standing by for Gmail or investor communication drafting."
    if agent_id == "muse":
        return "Standing by to polish copy, design direction, and demo presentation."
    if agent_id == "nexus":
        return "Standing by to turn the mission into roadmap and next steps."
    if task and task != "Standing by":
        return task
    if report:
        return report
    return "No active task yet. Mention this agent to assign one."


def _needs_from_user(agent_id: str, mission: AgentMission) -> str:
    if agent_id == "sentry" and mission.status == MissionStatus.WAITING_APPROVAL:
        return _approval_question(mission) or "Review the pending approval gate."
    if mission.status == MissionStatus.WAITING_APPROVAL and agent_id in {"prime", "forge"}:
        return _approval_question(mission) or "Approve or skip the pending mission action."
    return ""


def _agent_inspectors(
    *,
    mission: AgentMission,
    roster: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    graph_nodes: list[dict[str, Any]],
    forge_engine: str,
) -> list[dict[str, Any]]:
    report_by_agent = _last_by_agent(reports)
    files_written = [
        str(item)
        for item in mission.final_report.get("files_written", mission.files_touched[:16]) or []
    ]
    validation_commands = [
        str(item) for item in mission.final_report.get("validation_commands", []) or []
    ]
    if mission.final_report.get("run_command"):
        validation_commands.append(str(mission.final_report["run_command"]))
    base_evidence = [
        str(path)
        for path in (
            mission.final_report.get("forge_evidence_paths")
            or mission.final_report.get("evidence_paths")
            or []
        )
    ]
    if mission.final_report.get("evidence_log"):
        base_evidence.append(str(mission.final_report["evidence_log"]))

    nodes_by_id = {str(node.get("node_id")): node for node in graph_nodes}
    inspectors: list[dict[str, Any]] = []
    for row in roster:
        agent_id = str(row.get("agent_id", "")).lower()
        report = report_by_agent.get(agent_id, {})
        related_ids = list(_AGENT_NODE_MAP.get(agent_id, ()))
        if agent_id == forge_engine:
            related_ids = ["select_engine", "execute", "validate"]
        related_nodes = [nodes_by_id[node_id] for node_id in related_ids if node_id in nodes_by_id]
        node_evidence: list[str] = []
        for node in related_nodes:
            node_evidence.extend(str(path) for path in node.get("evidence") or [])
        status = str(row.get("status") or report.get("status") or "idle")
        current_task = str(row.get("task_summary") or "")
        last_report = str(report.get("report") or "")
        display_name = str(row.get("display_name") or report.get("agent") or agent_id.title())
        evidence_paths = sorted({*base_evidence, *node_evidence})
        files = files_written if agent_id in {"forge", forge_engine} else []
        commands = (
            validation_commands if agent_id in {"forge", "qa_engineer", "qa", forge_engine} else []
        )
        inspectors.append(
            {
                "agent_id": agent_id,
                "display_name": display_name,
                "role": _agent_role(agent_id),
                "status": status,
                "current_task": current_task
                if current_task and current_task != "Standing by"
                else "No active task yet. Mention this agent to assign one.",
                "last_report": last_report,
                "related_node_ids": related_ids,
                "related_nodes": related_nodes,
                "evidence_paths": evidence_paths,
                "files": files,
                "commands": commands,
                "what_doing": _what_doing(
                    agent_id,
                    task=current_task,
                    report=last_report,
                    mission=mission,
                    forge_engine=forge_engine,
                ),
                "needs_from_user": _needs_from_user(agent_id, mission),
                "ask_command": _agent_ask(agent_id, display_name),
                "metadata": {
                    "forge_engine": forge_engine if agent_id in {"forge", forge_engine} else "",
                    "build_status": str(mission.final_report.get("build_status", "")),
                    "risk_level": mission.risk_level,
                },
            }
        )
    return inspectors


def _work_feed(
    timeline: list[dict[str, Any]],
    *,
    graph_nodes: list[dict[str, Any]],
    forge_engine: str,
) -> list[dict[str, Any]]:
    evidence_by_agent: dict[str, list[str]] = {}
    for node in graph_nodes:
        agent_id = str(node.get("selected_agent") or "")
        if agent_id and node.get("evidence"):
            evidence_by_agent.setdefault(agent_id, []).extend(
                str(path) for path in node.get("evidence") or []
            )
    feed: list[dict[str, Any]] = []
    for index, entry in enumerate(timeline):
        agent_id = str(entry.get("agent_id") or "").lower()
        message = str(entry.get("summary") or "")
        if agent_id == "forge" and forge_engine and "engine" not in message.lower():
            message = f"{message} · engine={forge_engine}"
        feed.append(
            {
                "id": f"{index}-{agent_id or 'agent'}",
                "agent_id": agent_id,
                "agent": str(entry.get("agent") or "Agent"),
                "status": str(entry.get("status") or "done"),
                "message": message,
                "timestamp": entry.get("timestamp"),
                "evidence_paths": evidence_by_agent.get(agent_id, [])[:3],
            }
        )
    return feed


def _voice_status() -> dict[str, Any]:
    ow = openwakeword_status()
    wake_available = bool(ow.available)
    return {
        "wake_word_supported": wake_available,
        "wake_word_state": "available" if wake_available else "experimental",
        "fallback_message": (
            "Wake word available, but push-to-talk is recommended for demo."
            if wake_available
            else "Wake word is experimental. Use push-to-talk for demo."
        ),
        "mic_helper": "Click mic, speak command, release/auto-send.",
        "miss_message": "I didn't catch a wake phrase. Try push-to-talk or type the command.",
    }


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
    graph_nodes = _normalize_graph_nodes(
        (mission.artifacts.get("mission_graph") or {}).get("nodes", [])
    )
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
    forge_evidence = report.get("forge_evidence_paths") or []
    for forge_path in forge_evidence[:3]:
        actions.append(
            {
                "label": "Forge Evidence",
                "action": "copy_text",
                "text": forge_path,
            }
        )

    forge_engine = report.get("forge_engine") or (
        (mission.artifacts.get("mission_graph") or {}).get("engine_selected")
    )
    agent_reports = build_agent_reports(agent_timeline)
    war_room_roster = build_war_room_roster(
        agent_timeline,
        forge_engine=str(forge_engine or ""),
        mission_status=mission.status.value,
    )
    forge_engine_text = str(forge_engine or "")
    agent_inspectors = _agent_inspectors(
        mission=mission,
        roster=war_room_roster,
        reports=agent_reports,
        graph_nodes=graph_nodes,
        forge_engine=forge_engine_text,
    )
    agent_work_feed = _work_feed(
        agent_timeline,
        graph_nodes=graph_nodes,
        forge_engine=forge_engine_text,
    )

    return {
        "type": "agent_os_mission",
        "mission_id": mission.mission_id,
        "status": mission.status.value,
        "mission_title": mission.user_request,
        "agent_timeline": agent_timeline,
        "agent_reports": agent_reports,
        "war_room_roster": war_room_roster,
        "agent_inspectors": agent_inspectors,
        "agent_work_feed": agent_work_feed,
        "graph_nodes": graph_nodes,
        "mission_graph_nodes": graph_nodes,
        "voice_status": _voice_status(),
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
            "assumptions": report.get("assumptions", mission.artifacts.get("assumptions", [])),
            "app_spec_summary": report.get(
                "app_spec_summary", mission.artifacts.get("app_spec_summary")
            ),
            "files_written": report.get("files_written", mission.files_touched[:16]),
            "validation_commands": report.get("validation_commands", []),
            "forge_engine": report.get("forge_engine")
            or (mission.artifacts.get("mission_graph") or {}).get("engine_selected"),
            "engine_display_name": report.get("engine_display_name", ""),
            "engine_status": report.get("engine_status", ""),
            "engine_reason": report.get("engine_reason", ""),
            "setup_hint": report.get("setup_hint", ""),
            "external_engine_available": report.get("external_engine_available", False),
            "fallback_used": report.get("fallback_used", False),
            "forge_evidence_paths": report.get("forge_evidence_paths", []),
            "mission_graph_version": (mission.artifacts.get("mission_graph") or {}).get(
                "graph_version"
            ),
            "mission_graph_nodes": graph_nodes,
        },
        "actions": actions,
        "text": _short_text(mission),
    }
