"""MissionGraph runner — internal state machine with optional LangGraph adapter."""

from __future__ import annotations

import time
from typing import Any

from nova_core.mission_graph.config import MissionGraphRunConfig
from nova_core.mission_graph.models import (
    GRAPH_VERSION,
    NODE_DISPLAY_NAMES,
    MissionGraphEvidence,
    MissionGraphState,
    NodeRecord,
    NodeStatus,
    utc_now_iso,
)
from nova_core.mission_graph.nodes import NODE_HANDLERS, apply_node_update
from nova_core.mission_graph.store import MissionGraphStore


class MissionGraphRunner:
    NODE_ORDER: tuple[str, ...] = tuple(NODE_HANDLERS.keys())

    def __init__(self, store: MissionGraphStore | None = None) -> None:
        self.store = store or MissionGraphStore()

    def create_state(self, mission_id: str, user_request: str) -> MissionGraphState:
        nodes = [
            NodeRecord(node_id=node_id, display_name=NODE_DISPLAY_NAMES.get(node_id, node_id))
            for node_id in self.NODE_ORDER
        ]
        return MissionGraphState(mission_id=mission_id, user_request=user_request, nodes=nodes)

    def run(
        self,
        state: MissionGraphState,
        *,
        config: MissionGraphRunConfig | None = None,
    ) -> MissionGraphEvidence:
        if config is not None:
            state.engine_id = config.selected_engine
            state.context["_run_config"] = config
        for node_id in self.NODE_ORDER:
            record = state.node(node_id)
            if record is None:
                continue
            handler = NODE_HANDLERS[node_id]
            record.status = NodeStatus.RUNNING
            record.started_at = utc_now_iso()
            record.input_summary = state.user_request[:200]
            started = time.monotonic()
            try:
                update = handler(state)
            except Exception as exc:
                update = {"error": exc.__class__.__name__, "output_summary": str(exc)[:200]}
            apply_node_update(record, update, started=started)
            self._apply_state_update(state, update)
            state.snapshots.append(
                {
                    "node_id": node_id,
                    "engine_id": state.engine_id,
                    "commander": state.commander,
                    "timestamp": utc_now_iso(),
                }
            )
            if record.status == NodeStatus.FAILED:
                break
        evidence = MissionGraphEvidence.from_state(state)
        evidence.graph_version = GRAPH_VERSION
        self.store.save(evidence)
        return evidence

    def _apply_state_update(self, state: MissionGraphState, update: dict[str, Any]) -> None:
        if "commander" in update:
            state.commander = str(update["commander"])
        if "engine_id" in update:
            state.engine_id = str(update["engine_id"])
        if "context" in update and isinstance(update["context"], dict):
            state.context.update(update["context"])
        if "approvals" in update:
            state.approvals = list(update["approvals"])
        if "final_report" in update and isinstance(update["final_report"], dict):
            state.final_report.update(update["final_report"])
