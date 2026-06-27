"""NOVAGenie chat Agent OS structured payload tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.chat import ChatService
from nova_core.auth.principal import Principal
from nova_core.schemas.settings import Settings


@pytest.fixture
def workspace_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "nova-workspace"
    root.mkdir()
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(root))
    return root


def _mock_build_result(workspace_tmp: Path, app_type: str, name: str, dirname: str):
    from nova_core.orchestration.app_builder import BuildResult, CommandResult
    from nova_core.orchestration.preview import PreviewSession

    project = workspace_tmp / dirname
    return BuildResult(
        project_path=str(project),
        files_written=[str(project / "package.json")],
        install=CommandResult("npm install", str(project), 0, "", "", True),
        build=CommandResult("npm run build", str(project), 0, "", "", True),
        preview=PreviewSession(
            pid=99999,
            port=5173,
            url="http://127.0.0.1:5173",
            log_path="/tmp/p.log",
            reachable=True,
        ),
        preview_url="http://127.0.0.1:5173",
        build_passed=True,
        app_type=app_type,
        app_name=name,
        template_id=f"{app_type}_react_vite",
        runtime="web",
    )


@pytest.mark.asyncio
async def test_chat_returns_structured_agent_os_payload(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=test_settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(
            workspace_tmp, "calculator", "arth", "arth-calculator-app"
        )
        resp = await svc.handle_message(
            message="create a calculator app named arth",
            principal=principal,
        )
    payload = resp.get("agent_os_mission")
    assert payload is not None
    assert payload["type"] == "agent_os_mission"
    assert payload["mission_id"]
    agents = [entry["agent"] for entry in payload["agent_timeline"]]
    assert "Prime" in agents
    assert "Forge" in agents
    assert any("QA" in agent for agent in agents)
    assert any("Sentry" in agent for agent in agents)
    assert payload["result"]["preview_url"] == "http://127.0.0.1:5173"
    assert payload["result"]["approval_question"] == "Deploy this app?"
    labels = [action["label"] for action in payload["actions"]]
    assert "Yes" in labels
    assert "No" in labels
    assert "Open Preview" in labels


@pytest.mark.asyncio
async def test_chat_stream_routes_agent_os_not_general(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=test_settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(
            workspace_tmp, "calculator", "arth", "arth-calculator-app"
        )
        events = [
            event
            async for event in svc.stream_message(
                message="create a calculator app named arth",
                principal=principal,
            )
        ]
    done = next(event for event in events if event["event"] == "done")
    assert done["data"]["intent"] == "agent_os_mission"
    assert done["data"].get("agent_os_mission") is not None
    assert done["data"]["intent"] != "general"


@pytest.mark.asyncio
async def test_chat_no_skips_deployment(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=test_settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(
            workspace_tmp, "calculator", "arth", "arth-calculator-app"
        )
        await svc.handle_message(
            message="create a calculator app named arth",
            principal=principal,
        )
        skip = await svc.handle_message(message="no", principal=principal)
    assert skip["intent"] == "agent_os_deploy_no"
    assert "skipped" in skip["response"].lower()
    payload = skip.get("agent_os_mission")
    assert payload is not None
    assert payload["result"]["deployment_status"] == "skipped"


@pytest.mark.asyncio
async def test_chat_answers_war_room_awareness_from_latest_mission(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=test_settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(
            workspace_tmp, "calculator", "arth", "arth-calculator-app"
        )
        await svc.handle_message(
            message="create a calculator app named arth",
            principal=principal,
        )
    status = await svc.handle_message(message="what is Forge doing?", principal=principal)
    assert status["intent"] == "agent_awareness"
    assert "Forge" in status["response"]
    assert "Engine:" in status["response"]
