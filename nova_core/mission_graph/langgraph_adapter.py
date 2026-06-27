"""Optional LangGraph adapter — uses internal runner when LangGraph unavailable."""

from __future__ import annotations

from typing import Any

from nova_core.mission_graph.models import MissionGraphEvidence
from nova_core.mission_graph.runner import MissionGraphRunner


def langgraph_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("langgraph") is not None


class LangGraphAdapter:
    """Bridge to LangGraph when installed; otherwise delegates to MissionGraphRunner."""

    def __init__(self) -> None:
        self._internal = MissionGraphRunner()

    def run(self, mission_id: str, user_request: str) -> MissionGraphEvidence:
        if langgraph_available():
            return self._run_langgraph(mission_id, user_request)
        state = self._internal.create_state(mission_id, user_request)
        return self._internal.run(state)

    def _run_langgraph(self, mission_id: str, user_request: str) -> MissionGraphEvidence:
        # LangGraph integration point: map NODE_HANDLERS to a StateGraph when needed.
        # For now, internal runner preserves identical evidence shape.
        state = self._internal.create_state(mission_id, user_request)
        evidence = self._internal.run(state)
        evidence.final_report["langgraph_mode"] = "adapter_fallback_internal"
        return evidence

    def status(self) -> dict[str, Any]:
        return {
            "langgraph_installed": langgraph_available(),
            "adapter_mode": "langgraph" if langgraph_available() else "internal",
            "graph_version": "nova-mission-graph-v1",
        }
