"""MissionGraph data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

GRAPH_VERSION = "nova-mission-graph-v1"


class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class NodeRecord:
    node_id: str
    display_name: str
    status: NodeStatus = NodeStatus.PENDING
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    input_summary: str = ""
    output_summary: str = ""
    evidence: list[str] = field(default_factory=list)
    error: str | None = None
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "evidence": self.evidence,
            "error": self.error,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeRecord:
        return cls(
            node_id=str(data["node_id"]),
            display_name=str(data.get("display_name", data["node_id"])),
            status=NodeStatus(str(data.get("status", "pending"))),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            duration_ms=data.get("duration_ms"),
            input_summary=str(data.get("input_summary", "")),
            output_summary=str(data.get("output_summary", "")),
            evidence=list(data.get("evidence") or []),
            error=data.get("error"),
            retry_count=int(data.get("retry_count", 0)),
        )


MISSION_GRAPH_EDGES: list[tuple[str, str]] = [
    ("classify_request", "retrieve_context"),
    ("retrieve_context", "clarify_requirements"),
    ("clarify_requirements", "select_commander"),
    ("select_commander", "select_engine"),
    ("select_engine", "plan"),
    ("plan", "execute"),
    ("execute", "validate"),
    ("validate", "review"),
    ("review", "sentry_gate"),
    ("sentry_gate", "final_report"),
]

NODE_DISPLAY_NAMES: dict[str, str] = {
    "classify_request": "Classify Request",
    "retrieve_context": "Retrieve Context",
    "clarify_requirements": "Clarify Requirements",
    "select_commander": "Select Commander",
    "select_engine": "Select Engine",
    "plan": "Plan",
    "execute": "Execute",
    "validate": "Validate",
    "review": "Review",
    "sentry_gate": "Sentry Gate",
    "final_report": "Final Report",
}


@dataclass
class MissionGraphState:
    mission_id: str
    user_request: str
    commander: str = "Prime"
    engine_id: str = "deterministic_template"
    context: dict[str, Any] = field(default_factory=dict)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    final_report: dict[str, Any] = field(default_factory=dict)
    nodes: list[NodeRecord] = field(default_factory=list)
    snapshots: list[dict[str, Any]] = field(default_factory=list)

    def node(self, node_id: str) -> NodeRecord | None:
        for record in self.nodes:
            if record.node_id == node_id:
                return record
        return None


@dataclass
class MissionGraphEvidence:
    graph_version: str = GRAPH_VERSION
    mission_id: str = ""
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, str]] = field(default_factory=list)
    state_snapshots: list[dict[str, Any]] = field(default_factory=list)
    engine_selected: str = "deterministic_template"
    approvals: list[dict[str, Any]] = field(default_factory=list)
    final_report: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_version": self.graph_version,
            "mission_id": self.mission_id,
            "nodes": self.nodes,
            "edges": self.edges,
            "state_snapshots": self.state_snapshots,
            "engine_selected": self.engine_selected,
            "approvals": self.approvals,
            "final_report": self.final_report,
        }

    @classmethod
    def from_state(cls, state: MissionGraphState) -> MissionGraphEvidence:
        return cls(
            mission_id=state.mission_id,
            nodes=[n.to_dict() for n in state.nodes],
            edges=[{"from": a, "to": b} for a, b in MISSION_GRAPH_EDGES],
            state_snapshots=state.snapshots,
            engine_selected=state.engine_id,
            approvals=state.approvals,
            final_report=state.final_report,
        )


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
