"""MissionGraph node handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nova_core.forge.selector import suggest_forge_engine
from nova_core.mission_graph.models import MissionGraphState, NodeRecord, NodeStatus, utc_now_iso
from nova_core.orchestration.app_request import parse_app_request

NodeHandler = Callable[[MissionGraphState], dict[str, Any]]


def _classify_request(state: MissionGraphState) -> dict[str, Any]:
    parsed = parse_app_request(state.user_request)
    app_type = parsed.app_type if parsed else "general"
    return {
        "output_summary": f"mission_type={app_type}",
        "context": {**state.context, "app_type": app_type, "parsed": parsed is not None},
    }


def _retrieve_context(state: MissionGraphState) -> dict[str, Any]:
    return {
        "output_summary": "archive/memory context slot (local)",
        "context": {**state.context, "context_retrieved": True},
    }


def _clarify_requirements(state: MissionGraphState) -> dict[str, Any]:
    parsed = parse_app_request(state.user_request)
    vague = parsed is None or parsed.app_type in {"generic", "landing_page"}
    return {
        "output_summary": "clarification required" if vague else "requirements sufficient",
        "context": {**state.context, "needs_clarification": vague},
    }


def _select_commander(state: MissionGraphState) -> dict[str, Any]:
    app_type = state.context.get("app_type", "general")
    commander = "Forge" if app_type != "general" else "Prime"
    return {"commander": commander, "output_summary": f"commander={commander}"}


def _select_engine(state: MissionGraphState) -> dict[str, Any]:
    suggestion = suggest_forge_engine(state.user_request)
    return {
        "engine_id": suggestion.engine_id,
        "output_summary": suggestion.reason,
        "context": {
            **state.context,
            "engine_suggestion": suggestion.to_dict(),
            "complexity": suggestion.complexity,
        },
    }


def _plan(state: MissionGraphState) -> dict[str, Any]:
    return {
        "output_summary": f"plan via {state.engine_id}",
        "context": {**state.context, "planned": True},
    }


def _execute(state: MissionGraphState) -> dict[str, Any]:
    return {
        "output_summary": f"execute with {state.engine_id}",
        "context": {**state.context, "executed": True},
    }


def _validate(state: MissionGraphState) -> dict[str, Any]:
    ctx = {**state.context, "validated": True}
    return {"output_summary": "validation scheduled", "context": ctx}


def _review(state: MissionGraphState) -> dict[str, Any]:
    return {"output_summary": "review complete", "context": {**state.context, "reviewed": True}}


def _sentry_gate(state: MissionGraphState) -> dict[str, Any]:
    approval = {"action": "deploy", "status": "awaiting", "gate": "sentry"}
    approvals = [*state.approvals, approval]
    return {
        "output_summary": "sentry approval gate",
        "approvals": approvals,
        "context": {**state.context, "sentry_gated": True},
    }


def _final_report(state: MissionGraphState) -> dict[str, Any]:
    report = {
        "engine": state.engine_id,
        "commander": state.commander,
        "summary": f"Mission graph completed for {state.user_request[:80]}",
    }
    return {"final_report": report, "output_summary": "final report ready"}


NODE_HANDLERS: dict[str, NodeHandler] = {
    "classify_request": _classify_request,
    "retrieve_context": _retrieve_context,
    "clarify_requirements": _clarify_requirements,
    "select_commander": _select_commander,
    "select_engine": _select_engine,
    "plan": _plan,
    "execute": _execute,
    "validate": _validate,
    "review": _review,
    "sentry_gate": _sentry_gate,
    "final_report": _final_report,
}


def apply_node_update(record: NodeRecord, update: dict[str, Any], *, started: float) -> None:
    import time

    record.status = NodeStatus.DONE
    record.finished_at = utc_now_iso()
    record.duration_ms = int((time.monotonic() - started) * 1000)
    record.output_summary = str(update.get("output_summary", ""))
    if update.get("error"):
        record.status = NodeStatus.FAILED
        record.error = str(update["error"])
    evidence = update.get("evidence")
    if isinstance(evidence, list):
        record.evidence.extend(str(item) for item in evidence)
