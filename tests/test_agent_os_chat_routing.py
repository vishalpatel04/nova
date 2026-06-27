"""Chat routing tests for Agent OS app-building commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.chat import ChatService
from nova_core.auth.principal import Principal
from nova_core.orchestration.app_request import is_app_build_intent, parse_app_request
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


@pytest.mark.parametrize(
    ("message", "app_type", "app_name"),
    [
        ("create a calculator app named arth", "calculator", "arth"),
        ("make a calculator app called arth", "calculator", "arth"),
        ("create a simple command-line calculator app named arth", "cli_calculator", "arth"),
        ("build a landing page for SusCo", "landing_page", "SusCo Landing Page"),
        ("build a todo app called mytasks", "todo", "mytasks"),
    ],
)
def test_named_app_request_parsing(message: str, app_type: str, app_name: str) -> None:
    parsed = parse_app_request(message)
    assert parsed is not None
    assert parsed.app_type == app_type
    assert parsed.app_name == app_name
    assert is_app_build_intent(message)


def test_command_line_app_without_type_requires_clarification() -> None:
    parsed = parse_app_request("create a command-line app named demo")
    assert parsed is not None
    assert parsed.requires_clarification is True
    assert "CLI app or a web app" in parsed.clarification_message


@pytest.mark.asyncio
async def test_chat_named_calculator_routes_to_agent_os(
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
    assert resp["intent"] == "agent_os_mission"
    assert resp["intent"] != "general"
    assert "save this script as" not in resp["response"].lower()
    assert "Prime" in resp["response"]
    assert "Mission ID:" in resp["response"]
    assert "Evidence log:" in resp["response"]
    assert "Deploy this app?" in resp["response"]


@pytest.mark.asyncio
async def test_chat_cli_calculator_routes_to_agent_os_not_qwen(
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
    from nova_core.orchestration.app_builder import BuildResult, CommandResult

    project = workspace_tmp / "arth-cli-calculator"
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = BuildResult(
            project_path=str(project),
            files_written=[str(project / "calculator.py")],
            install=CommandResult("py_compile", str(project), 0, "", "", True),
            build=CommandResult("smoke", str(project), 0, "smoke: PASS", "", True),
            preview=None,
            preview_url=None,
            build_passed=True,
            app_type="cli_calculator",
            app_name="arth",
            template_id="cli_calculator_python",
            runtime="cli",
            run_command=f"python3 {project / 'calculator.py'}",
        )
        resp = await svc.handle_message(
            message="create a simple command-line calculator app named arth",
            principal=principal,
        )
    assert resp["intent"] == "agent_os_mission"
    assert "save this script as" not in resp["response"].lower()
    assert "Package this app?" in resp["response"]


@pytest.mark.asyncio
async def test_chat_ambiguous_cli_requests_clarification_not_qwen(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=test_settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )
    resp = await svc.handle_message(
        message="create a command-line app named demo",
        principal=principal,
    )
    assert resp["intent"] == "agent_os_mission"
    assert resp["intent"] != "general"
    assert "CLI app or a web app" in resp["response"]


@pytest.mark.asyncio
async def test_chat_named_calculator_writes_files_in_workspace(
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
    resp = await svc.handle_message(
        message="create a calculator app named arth",
        principal=principal,
    )
    project = workspace_tmp / "arth-calculator-app"
    assert (project / "package.json").exists()
    assert (project / "src" / "App.tsx").exists()
    assert "Mission ID:" in resp["response"]
    assert (workspace_tmp / ".nova-runs").exists()
