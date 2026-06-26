"""Agent OS domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any


class MissionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PermissionLevel(IntEnum):
    READ_LOCAL = 0
    WORKSPACE_WRITE = 1
    ROUTINE_EXTERNAL = 2
    HIGH_IMPACT = 3
    MANUAL_ONLY = 4


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    display_name: str
    department: str
    role: str
    mission_scope: str
    allowed_tools: tuple[str, ...]
    blocked_tools: tuple[str, ...]
    definition_of_done: str
    risk_level: str
    output_schema: str
    when_to_activate: str


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    name: str
    description: str
    department: str
    required_permission_level: PermissionLevel
    requires_approval: bool
    allowed_paths: tuple[str, ...]
    tools_used: tuple[str, ...]
    input_schema: str
    output_schema: str
    validator: str
    audit_fields: tuple[str, ...]


@dataclass
class TimelineEvent:
    agent_id: str
    display_name: str
    message: str
    timestamp: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMission:
    mission_id: str
    user_request: str
    mission_type: str
    commander: str
    squad: list[str]
    status: MissionStatus
    risk_level: str
    acceptance_criteria: list[str]
    timeline_events: list[TimelineEvent]
    skill_calls: list[dict[str, Any]]
    files_touched: list[str]
    commands_run: list[dict[str, Any]]
    validation_results: list[dict[str, Any]]
    approvals_required: list[str]
    artifacts: dict[str, Any]
    final_report: dict[str, Any]
    created_at: str
    updated_at: str
    workspace_path: str = ""
    preview_url: str | None = None
    evidence_log_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "user_request": self.user_request,
            "mission_type": self.mission_type,
            "commander": self.commander,
            "squad": self.squad,
            "status": self.status.value,
            "risk_level": self.risk_level,
            "acceptance_criteria": self.acceptance_criteria,
            "timeline_events": [
                {
                    "agent_id": e.agent_id,
                    "display_name": e.display_name,
                    "message": e.message,
                    "timestamp": e.timestamp,
                    "evidence": e.evidence,
                }
                for e in self.timeline_events
            ],
            "skill_calls": self.skill_calls,
            "files_touched": self.files_touched,
            "commands_run": self.commands_run,
            "validation_results": self.validation_results,
            "approvals_required": self.approvals_required,
            "artifacts": self.artifacts,
            "final_report": self.final_report,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "workspace_path": self.workspace_path,
            "preview_url": self.preview_url,
            "evidence_log_path": self.evidence_log_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentMission:
        events = [
            TimelineEvent(
                agent_id=e["agent_id"],
                display_name=e["display_name"],
                message=e["message"],
                timestamp=e["timestamp"],
                evidence=e.get("evidence", {}),
            )
            for e in data.get("timeline_events", [])
        ]
        return cls(
            mission_id=data["mission_id"],
            user_request=data["user_request"],
            mission_type=data["mission_type"],
            commander=data["commander"],
            squad=list(data.get("squad", [])),
            status=MissionStatus(data.get("status", MissionStatus.PENDING.value)),
            risk_level=data.get("risk_level", "medium"),
            acceptance_criteria=list(data.get("acceptance_criteria", [])),
            timeline_events=events,
            skill_calls=list(data.get("skill_calls", [])),
            files_touched=list(data.get("files_touched", [])),
            commands_run=list(data.get("commands_run", [])),
            validation_results=list(data.get("validation_results", [])),
            approvals_required=list(data.get("approvals_required", [])),
            artifacts=dict(data.get("artifacts", {})),
            final_report=dict(data.get("final_report", {})),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            workspace_path=data.get("workspace_path", ""),
            preview_url=data.get("preview_url"),
            evidence_log_path=data.get("evidence_log_path"),
        )


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()
