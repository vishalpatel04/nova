"""Tests for NOVA Agent OS and general app builder."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.agent_mission_service import (
    is_agent_os_mission_request,
    is_memory_status_request,
    is_system_memory_status_request,
    normalize_build_app_request,
    parse_archive_search_query,
    resolve_deployment_chat_intent,
)
from apps.api.services.chat import ChatService
from nova_core.agent_os.mission import AgentMissionRunner, MissionStore
from nova_core.agent_os.models import MissionStatus, PermissionLevel
from nova_core.agent_os.registry import LEADERSHIP_AGENTS, list_forge_specialists
from nova_core.agent_os.sentry import review_action, sanitize_log_line
from nova_core.agent_os.skills import SKILL_REGISTRY
from nova_core.agent_os.workspace import assert_workspace_write, is_within_workspace, redact_secrets
from nova_core.auth.principal import Principal
from nova_core.memory.access_policy import AccessProfile, resolve_access_policy
from nova_core.orchestration.app_builder import (
    CALCULATOR_FILES,
    expected_calculator_files,
    project_path_for_request,
    stop_app_preview,
    write_calculator_files,
)
from nova_core.orchestration.app_request import AppRequest, parse_app_request, project_dir_name
from nova_core.orchestration.app_spec import build_app_spec
from nova_core.orchestration.preview import find_free_port, is_port_available
from nova_core.orchestration.templates import get_template, template_for_spec
from nova_core.schemas.settings import Settings


@pytest.fixture
def workspace_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "nova-workspace"
    root.mkdir()
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(root))
    return root


def _app_request(app_type: str, text: str, name: str) -> AppRequest:
    return AppRequest(
        raw_user_request=text,
        app_type=app_type,
        app_name=name,
        features=(),
        style_preference="modern",
        deployment_requested=False,
        requires_clarification=False,
    )


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
            pid=99999, port=5173, url="http://127.0.0.1:5173", log_path="/tmp/p.log", reachable=True
        ),
        preview_url="http://127.0.0.1:5173",
        build_passed=True,
        app_type=app_type,
        app_name=name,
        template_id=f"{app_type}_react_vite",
    )


def test_leadership_agents_present() -> None:
    required = {"prime", "forge", "nexus", "orbit", "muse", "archive", "sentry"}
    assert required.issubset(LEADERSHIP_AGENTS.keys())


def test_forge_specialists_present() -> None:
    required = {
        "product_planner",
        "architect",
        "frontend_engineer",
        "backend_engineer",
        "qa_engineer",
        "fixer",
        "code_reviewer",
        "devops_deploy",
        "release_manager",
        "security_reviewer",
    }
    assert required.issubset({s.id for s in list_forge_specialists()})


def test_skill_registry_required_skills() -> None:
    required = {
        "archive.search_local",
        "archive.memory_status",
        "file.write_project_file",
        "file.read_local",
        "shell.npm_install",
        "shell.npm_build",
        "shell.npm_dev",
        "git.status",
        "deploy.vercel_prepare",
        "deploy.vercel_deploy",
        "browser.open_preview",
        "sentry.review_action",
    }
    assert required.issubset(SKILL_REGISTRY.keys())


def test_skill_permission_levels() -> None:
    assert (
        SKILL_REGISTRY["archive.search_local"].required_permission_level
        == PermissionLevel.READ_LOCAL
    )
    assert SKILL_REGISTRY["deploy.vercel_deploy"].requires_approval is True
    assert (
        SKILL_REGISTRY["file.write_project_file"].required_permission_level
        == PermissionLevel.WORKSPACE_WRITE
    )


def test_full_local_profile_allows_home(memory_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nova_core.memory.access_policy.Path.home", lambda: memory_home)
    policy = resolve_access_policy(profile=AccessProfile.FULL_LOCAL)
    assert policy.is_path_allowed(str(memory_home / "Documents" / "lund.txt"))


def test_memory_status_routing() -> None:
    assert is_memory_status_request("memory status")
    assert not is_memory_status_request("system memory status")


def test_system_memory_status_routing() -> None:
    assert is_system_memory_status_request("system memory status")
    assert is_system_memory_status_request("ram usage")


def test_archive_search_query_parsing() -> None:
    assert parse_archive_search_query("can you find Lund in my pc") == "Lund"
    assert parse_archive_search_query("search my Mac for reimbursement") == "reimbursement"


@pytest.mark.parametrize(
    ("text", "app_type"),
    [
        ("build a calculator app", "calculator"),
        ("make a todo app", "todo"),
        ("build a habit tracker app", "habit_tracker"),
        ("create an expense tracker", "expense_tracker"),
        ("build a landing page for SusCo", "landing_page"),
        ("build a simple web app for pet sitting", "generic"),
    ],
)
def test_app_request_parser(text: str, app_type: str) -> None:
    parsed = parse_app_request(text)
    assert parsed is not None
    assert parsed.app_type == app_type


def test_app_spec_generated_for_each_type() -> None:
    for app_type, text, _name in (
        ("calculator", "build a calculator app", "NOVA Calculator"),
        ("todo", "build a todo app", "NOVA Todo"),
        ("habit_tracker", "build a habit tracker", "NOVA Habit Tracker"),
        ("expense_tracker", "build an expense tracker", "NOVA Expense Tracker"),
        ("landing_page", "build a landing page for Acme", "Acme Landing Page"),
        ("generic", "build a simple web app for ideas", "ideas"),
    ):
        request = parse_app_request(text)
        assert request is not None
        spec = build_app_spec(request)
        assert spec.app_type == app_type
        assert spec.stack == "Vite + React + TypeScript"
        assert spec.acceptance_criteria


@pytest.mark.parametrize(
    ("app_type", "dirname"),
    [
        ("calculator", "calculator-app"),
        ("todo", "todo-app"),
        ("habit_tracker", "habit-tracker-app"),
        ("expense_tracker", "expense-tracker-app"),
    ],
)
def test_template_creates_expected_files(workspace_tmp: Path, app_type: str, dirname: str) -> None:
    text = f"build a {app_type.replace('_', ' ')} app"
    request = parse_app_request(text)
    assert request is not None
    spec = build_app_spec(request)
    template = template_for_spec(spec)
    project = workspace_tmp / project_dir_name(request)
    files = template.build_files(spec)
    for rel, content in files.items():
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    assert (project / "package.json").exists()
    assert (project / "src/App.tsx").exists()
    assert (project / "README.md").exists()
    pkg = json.loads((project / "package.json").read_text(encoding="utf-8"))
    assert "dev" in pkg["scripts"]
    assert "build" in pkg["scripts"]
    assert "react" in pkg["dependencies"]


def test_landing_and_generic_templates(workspace_tmp: Path) -> None:
    for text in (
        "build a landing page for my startup",
        "build a simple web app for investor demo",
    ):
        request = parse_app_request(text)
        assert request is not None
        spec = build_app_spec(request)
        files = template_for_spec(spec).build_files(spec)
        assert "src/App.tsx" in files
        assert "package.json" in files


def test_agent_os_mission_trigger() -> None:
    assert is_agent_os_mission_request("build a calculator app, test it, preview it")
    assert is_agent_os_mission_request("build a todo app")


def test_calculator_files_written(workspace_tmp: Path) -> None:
    project = workspace_tmp / "calculator-app"
    files = write_calculator_files(project)
    assert len(files) == len(CALCULATOR_FILES)
    for path in expected_calculator_files(project):
        assert path.exists()


def test_package_json_react_typescript(workspace_tmp: Path) -> None:
    project = workspace_tmp / "calculator-app"
    write_calculator_files(project)
    pkg = json.loads((project / "package.json").read_text(encoding="utf-8"))
    assert "react" in pkg["dependencies"]
    assert "typescript" in pkg["devDependencies"]


def test_calculator_mission_timeline(workspace_tmp: Path) -> None:
    runs = workspace_tmp / ".nova-runs"
    runs.mkdir(parents=True, exist_ok=True)
    runner = AgentMissionRunner(MissionStore(runs))
    with patch("nova_core.agent_os.mission.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(
            workspace_tmp, "calculator", "NOVA Calculator", "calculator-app"
        )
        mission = runner.run_mission(
            "build a calculator app, test it, preview it, and prepare deployment",
            run_npm=False,
        )
    names = [e.display_name for e in mission.timeline_events]
    for required in (
        "Prime",
        "Archive",
        "Forge",
        "Product Planner",
        "Architect",
        "Frontend Engineer",
        "QA Engineer",
        "Code Reviewer",
        "Deploy Engineer",
        "Sentry",
    ):
        assert required in names
    assert mission.final_report.get("build_status") == "PASS"
    assert mission.preview_url == "http://127.0.0.1:5173"
    assert mission.status == MissionStatus.WAITING_APPROVAL
    output = runner.format_cli_output(mission)
    assert "Deploy this app?" in output


def test_preview_url_only_when_reachable(workspace_tmp: Path) -> None:
    runs = workspace_tmp / ".nova-runs"
    runs.mkdir(parents=True, exist_ok=True)
    runner = AgentMissionRunner(MissionStore(runs))
    with patch("nova_core.agent_os.mission.build_app") as mock_build:
        from nova_core.orchestration.app_builder import BuildResult, CommandResult
        from nova_core.orchestration.preview import PreviewSession

        project = workspace_tmp / "todo-app"
        mock_build.return_value = BuildResult(
            project_path=str(project),
            files_written=[],
            install=CommandResult("npm install", str(project), 0, "", "", True),
            build=CommandResult("npm run build", str(project), 0, "", "", True),
            preview=PreviewSession(
                pid=1,
                port=5173,
                url="http://127.0.0.1:5173",
                log_path="/tmp/x.log",
                reachable=False,
            ),
            preview_url=None,
            build_passed=True,
            app_type="todo",
            app_name="NOVA Todo",
            template_id="todo_react_vite",
        )
        mission = runner.run_mission("build a todo app", run_npm=False)
    assert mission.preview_url is None
    deploy_messages = [
        e.message.lower() for e in mission.timeline_events if e.agent_id == "devops_deploy"
    ]
    assert any("failed" in message for message in deploy_messages)


def test_busy_port_selects_next_free() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        assert not is_port_available(port)
        free = find_free_port(port + 1, max_tries=5)
        assert free == port + 1


def test_stop_preview_invalid_pid() -> None:
    assert stop_app_preview(None) is False
    assert stop_app_preview(-1) is False


def test_mission_final_response_asks_deploy(workspace_tmp: Path) -> None:
    runs = workspace_tmp / ".nova-runs"
    runs.mkdir(parents=True, exist_ok=True)
    runner = AgentMissionRunner(MissionStore(runs))
    with patch("nova_core.agent_os.mission.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(workspace_tmp, "todo", "NOVA Todo", "todo-app")
        mission = runner.run_mission("build a todo app", run_npm=False)
    text = runner.format_cli_output(mission)
    assert "Deploy this app?" in text
    assert "yes" in text
    assert "no" in text


def test_yes_maps_to_deploy_only_when_awaiting(workspace_tmp: Path) -> None:
    runs = workspace_tmp / ".nova-runs"
    runs.mkdir(parents=True, exist_ok=True)
    runner = AgentMissionRunner(MissionStore(runs))
    with patch("nova_core.agent_os.mission.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(workspace_tmp, "todo", "NOVA Todo", "todo-app")
        runner.run_mission("build a todo app", run_npm=False)
    assert resolve_deployment_chat_intent("yes") == ("agent_os_deploy_yes", {})


def test_yes_without_awaiting_mission_is_safe(workspace_tmp: Path) -> None:
    runs = workspace_tmp / ".nova-runs"
    runs.mkdir(parents=True, exist_ok=True)
    assert AgentMissionRunner(MissionStore(runs)).latest_awaiting_approval() is None
    assert resolve_deployment_chat_intent("yes") is None


def test_no_marks_deploy_skipped(workspace_tmp: Path) -> None:
    runs = workspace_tmp / ".nova-runs"
    runs.mkdir(parents=True, exist_ok=True)
    runner = AgentMissionRunner(MissionStore(runs))
    with patch("nova_core.agent_os.mission.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(workspace_tmp, "todo", "NOVA Todo", "todo-app")
        mission = runner.run_mission("build a todo app", run_npm=False)
    skipped = runner.skip_deployment(mission.mission_id)
    assert skipped.final_report["deployment_status"] == "skipped"
    assert skipped.status == MissionStatus.COMPLETED


def test_deploy_requires_sentry_approval(workspace_tmp: Path) -> None:
    verdict = review_action("deploy.vercel_deploy")
    assert verdict.requires_approval is True
    runs = workspace_tmp / ".nova-runs"
    runs.mkdir(parents=True, exist_ok=True)
    runner = AgentMissionRunner(MissionStore(runs))
    with patch("nova_core.agent_os.mission.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(
            workspace_tmp, "calculator", "NOVA Calculator", "calculator-app"
        )
        mission = runner.run_mission("build a calculator app", run_npm=False)
    deployed = runner.deploy_mission(mission.mission_id)
    sentry_events = [e for e in deployed.timeline_events if e.agent_id == "sentry"]
    assert any("approval" in e.message.lower() for e in sentry_events)


def test_deployment_approval_gated() -> None:
    verdict = review_action("deploy.vercel_deploy")
    assert verdict.requires_approval is True


def test_destructive_commands_blocked() -> None:
    verdict = review_action("rm -rf /")
    assert verdict.allowed is False


def test_secrets_redacted() -> None:
    text = "api_key=supersecretvalue"
    assert "supersecretvalue" not in redact_secrets(text)
    sanitized = sanitize_log_line("password=abc123")
    assert "abc123" not in sanitized
    assert "[REDACTED]" in sanitized


def test_writes_outside_workspace_blocked(workspace_tmp: Path) -> None:
    with pytest.raises(PermissionError):
        assert_workspace_write("/tmp/outside")


def test_writes_inside_workspace_allowed(workspace_tmp: Path) -> None:
    target = workspace_tmp / "calculator-app" / "README.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    resolved = assert_workspace_write(target)
    assert is_within_workspace(resolved)


def test_npm_commands_workspace_scoped(workspace_tmp: Path) -> None:
    request = parse_app_request("build a todo app")
    assert request is not None
    path = project_path_for_request(request, workspace_tmp)
    assert str(path).startswith(str(workspace_tmp))


def test_normalize_build_app_request() -> None:
    assert "todo" in normalize_build_app_request("todo app")
    assert "landing page" in normalize_build_app_request("landing page for SusCo")


def test_get_template_fallback() -> None:
    assert get_template("unknown").template_id == "generic_react_vite"


@pytest.mark.asyncio
async def test_chat_memory_status_not_ram(
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
    resp = await svc.handle_message(message="memory status", principal=principal)
    assert "NOVA memory status" in resp["response"]
    assert "RAM" not in resp["response"]


@pytest.mark.asyncio
async def test_chat_system_memory_status_is_ram(
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
    resp = await svc.handle_message(message="system memory status", principal=principal)
    assert resp["intent"] == "system_memory_status"
    assert "RAM" in resp["response"] or "System memory status" in resp["response"]


@pytest.mark.asyncio
async def test_chat_archive_search_intent(
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
    resp = await svc.handle_message(message="can you find Lund in my pc", principal=principal)
    assert resp["intent"] == "archive_search"
    assert "File Explorer" not in resp["response"]
    assert "Win + E" not in resp["response"]
    assert "don't have direct access" not in resp["response"].lower()


@pytest.mark.asyncio
async def test_chat_calculator_mission_not_general(
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
    with patch("nova_core.agent_os.mission.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(
            workspace_tmp, "calculator", "NOVA Calculator", "calculator-app"
        )
        resp = await svc.handle_message(
            message="build a calculator app, test it, preview it, and prepare deployment",
            principal=principal,
        )
    assert resp["intent"] == "agent_os_mission"
    assert resp["intent"] != "general"
    assert "Prime" in resp["response"]
    assert "Deploy this app?" in resp["response"]


@pytest.mark.asyncio
async def test_chat_todo_mission_not_general(
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
    with patch("nova_core.agent_os.mission.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(workspace_tmp, "todo", "NOVA Todo", "todo-app")
        resp = await svc.handle_message(message="make a todo app", principal=principal)
    assert resp["intent"] == "agent_os_mission"
    assert "Deploy this app?" in resp["response"]


@pytest.fixture
def memory_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    (home / "Documents" / "lund.txt").write_text("lund", encoding="utf-8")
    return home
