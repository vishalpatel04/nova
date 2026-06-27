"""Live Forge engine selection in NOVAGenie chat and mission execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.chat import ChatService
from nova_core.agent_os.chat_payload import build_agent_os_chat_payload
from nova_core.agent_os.mission import AgentMissionRunner, MissionStore
from nova_core.forge.mission_executor import ForgeExecutionResult
from nova_core.mission_graph.config import MissionGraphRunConfig
from nova_core.mission_graph.runner import MissionGraphRunner
from nova_core.mission_graph.store import MissionGraphStore
from nova_core.models.enums import PendingToolIntentType
from nova_core.models.orm import PendingToolIntent
from nova_core.orchestration.app_builder import BuildResult, CommandResult
from nova_core.schemas.settings import Settings


@pytest.fixture
def workspace_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "nova-workspace"
    root.mkdir()
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(root))
    return root


def _principal(settings: Settings):
    from nova_core.auth.principal import Principal

    return Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )


def _mock_build(workspace_tmp: Path) -> BuildResult:
    project = workspace_tmp / "expense-tracker-proper"
    return BuildResult(
        project_path=str(project),
        files_written=[str(project / "package.json")],
        install=CommandResult("npm install", str(project), 0, "", "", True),
        build=CommandResult("npm run build", str(project), 0, "", "", True),
        preview=None,
        preview_url=None,
        build_passed=True,
        app_type="expense_tracker",
        app_name="proper",
        template_id="expense_tracker_v1",
    )


async def _session_id_from_first_message(
    svc: ChatService,
    principal: Any,
    message: str,
) -> tuple[str, dict[str, Any]]:
    resp = await svc.handle_message(message=message, principal=principal)
    session_id = resp.get("session_id")
    assert session_id
    return str(session_id), resp


@pytest.mark.asyncio
async def test_complex_app_creates_forge_engine_selection_pending(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    _session_id, resp = await _session_id_from_first_message(
        svc,
        principal,
        "build a proper expense tracker with login and database",
    )
    assert resp["intent"] == "forge_engine_selection"
    assert "Forge engines" in resp["response"] or "Forge engine" in resp["response"]
    result = await db_session.execute(select(PendingToolIntent))
    records = result.scalars().all()
    assert any(r.intent_type == PendingToolIntentType.FORGE_ENGINE_SELECTION.value for r in records)


@pytest.mark.asyncio
async def test_explicit_openhands_routes_to_selection_when_unavailable(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    _session_id, resp = await _session_id_from_first_message(
        svc,
        principal,
        "use OpenHands to improve this app",
    )
    assert resp["intent"] in {"forge_engine_selection", "agent_os_mission"}
    if resp["intent"] == "forge_engine_selection":
        assert "OpenHands" in resp["response"]


@pytest.mark.asyncio
async def test_unavailable_openhands_shows_setup_hint_not_silent_fallback(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    session_id, _first = await _session_id_from_first_message(
        svc,
        principal,
        "build a proper expense tracker with login and database",
    )
    resp = await svc.handle_message(
        message="use openhands",
        principal=principal,
        session_id=session_id,
    )
    assert "OpenHands" in resp["response"]
    assert resp["intent"] == "forge_engine_selection"
    assert "agent_os_mission" not in resp or resp.get("agent_os_mission") is None


@pytest.mark.asyncio
async def test_deterministic_fallback_consumes_pending_and_runs_mission(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = _mock_build(workspace_tmp)
        session_id, _first = await _session_id_from_first_message(
            svc,
            principal,
            "build a proper expense tracker with login and database",
        )
        resp = await svc.handle_message(
            message="use deterministic fallback",
            principal=principal,
            session_id=session_id,
        )
    assert resp["intent"] == "agent_os_mission"
    payload = resp.get("agent_os_mission")
    assert payload is not None
    assert payload["result"]["forge_engine"] == "deterministic_template"
    assert payload["result"]["fallback_used"] is True


def test_mission_graph_execute_calls_selected_engine(
    workspace_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(workspace_tmp))
    mock_result = ForgeExecutionResult(
        engine_id="openhands",
        status="success",
        workspace_path=str(workspace_tmp / "demo"),
        build_passed=True,
        app_name="demo",
        app_type="generic",
        engine_display_name="OpenHands",
    )
    with patch(
        "nova_core.mission_graph.nodes.execute_forge_build",
        return_value=mock_result,
    ) as mock_exec:
        runner = MissionGraphRunner(store=MissionGraphStore(base_dir=workspace_tmp / "graphs"))
        state = runner.create_state("mid-exec", "build demo app")
        config = MissionGraphRunConfig(selected_engine="openhands", settings=Settings())
        evidence = runner.run(state, config=config)
        mock_exec.assert_called_once()
        assert evidence.final_report.get("forge_execution", {}).get("engine_id") == "openhands"


@pytest.mark.asyncio
async def test_simple_calculator_still_runs_deterministic_demo(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = BuildResult(
            project_path=str(workspace_tmp / "arth-calculator-app"),
            files_written=[str(workspace_tmp / "arth-calculator-app" / "package.json")],
            install=CommandResult("npm install", str(workspace_tmp), 0, "", "", True),
            build=CommandResult("npm run build", str(workspace_tmp), 0, "", "", True),
            preview=None,
            preview_url=None,
            build_passed=True,
            app_type="calculator",
            app_name="arth",
            template_id="calculator_v1",
        )
        resp = await svc.handle_message(
            message="create a calculator app named arth",
            principal=principal,
        )
    assert resp["intent"] == "agent_os_mission"
    payload = resp.get("agent_os_mission")
    assert payload is not None
    assert payload["result"]["forge_engine"] == "deterministic_template"


def test_structured_payload_includes_forge_engine_and_graph_nodes(
    workspace_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(workspace_tmp))
    store = MissionStore(base_dir=workspace_tmp / "runs")
    runner = AgentMissionRunner(store=store, settings=Settings())
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = _mock_build(workspace_tmp)
        mission = runner.run_mission(
            "build a calculator app named demo",
            selected_engine="deterministic_template",
        )
    payload = build_agent_os_chat_payload(mission)
    assert payload["result"]["forge_engine"] == "deterministic_template"
    assert payload["mission_graph_nodes"]
    assert payload["graph_nodes"]


@pytest.mark.asyncio
async def test_unavailable_engine_does_not_crash_non_stream_chat(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    session_id, _first = await _session_id_from_first_message(
        svc,
        principal,
        "build a CRM with auth and analytics",
    )
    resp = await svc.handle_message(
        message="use openhands",
        principal=principal,
        session_id=session_id,
    )
    assert resp["response"]
    assert resp["intent"] == "forge_engine_selection"


@pytest.mark.asyncio
async def test_stream_and_non_stream_forge_selection_match(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    _session_id, non_stream = await _session_id_from_first_message(
        svc,
        principal,
        "build a proper expense tracker with login and database",
    )
    events = [
        event
        async for event in svc.stream_message(
            message="build a CRM with auth and analytics",
            principal=principal,
        )
    ]
    done = next(event for event in events if event["event"] == "done")
    assert non_stream["intent"] == "forge_engine_selection"
    assert done["data"]["intent"] == "forge_engine_selection"


def test_evidence_json_records_selected_engine(
    workspace_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(workspace_tmp))
    store = MissionStore(base_dir=workspace_tmp / "runs")
    runner = AgentMissionRunner(store=store, settings=Settings())
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = _mock_build(workspace_tmp)
        mission = runner.run_mission(
            "build a todo app named evidence-demo",
            selected_engine="deterministic_template",
            allow_fallback=True,
        )
    graph = mission.artifacts.get("mission_graph") or {}
    assert graph.get("engine_selected") == "deterministic_template"
    assert mission.final_report.get("forge_engine") == "deterministic_template"


@pytest.mark.asyncio
async def test_sentry_still_gates_deploy_after_forge_mission(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = BuildResult(
            project_path=str(workspace_tmp / "arth-calculator-app"),
            files_written=[str(workspace_tmp / "arth-calculator-app" / "package.json")],
            install=CommandResult("npm install", str(workspace_tmp), 0, "", "", True),
            build=CommandResult("npm run build", str(workspace_tmp), 0, "", "", True),
            preview=None,
            preview_url="http://127.0.0.1:5173",
            build_passed=True,
            app_type="calculator",
            app_name="arth",
            template_id="calculator_v1",
        )
        resp = await svc.handle_message(
            message="create a calculator app named arth",
            principal=principal,
        )
    payload = resp.get("agent_os_mission")
    assert payload is not None
    assert payload["result"]["approval_question"] == "Deploy this app?"
    assert any(action["label"] == "Yes" for action in payload["actions"])
