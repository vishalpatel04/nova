"""Tests for NOVA Agent OS v1."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.agent_mission_service import (
    is_agent_os_mission_request,
    is_memory_status_request,
    is_system_memory_status_request,
    parse_archive_search_query,
)
from apps.api.services.chat import ChatService
from nova_core.agent_os.mission import AgentMissionRunner, MissionStore
from nova_core.agent_os.models import PermissionLevel
from nova_core.agent_os.registry import LEADERSHIP_AGENTS, list_forge_specialists
from nova_core.agent_os.sentry import review_action, sanitize_log_line
from nova_core.agent_os.skills import SKILL_REGISTRY
from nova_core.agent_os.workspace import assert_workspace_write, is_within_workspace, redact_secrets
from nova_core.auth.principal import Principal
from nova_core.memory.access_policy import AccessProfile, resolve_access_policy
from nova_core.orchestration.app_builder import (
    CALCULATOR_FILES,
    expected_calculator_files,
    write_calculator_files,
)
from nova_core.schemas.settings import Settings


@pytest.fixture
def workspace_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "nova-workspace"
    root.mkdir()
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(root))
    return root


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


def test_agent_os_mission_trigger() -> None:
    assert is_agent_os_mission_request("build a calculator app, test it, preview it")


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
    with patch("nova_core.agent_os.mission.build_calculator_app") as mock_build:
        from nova_core.orchestration.app_builder import BuildResult, CommandResult

        mock_build.return_value = BuildResult(
            project_path=str(workspace_tmp / "calculator-app"),
            files_written=[str(workspace_tmp / "calculator-app" / "package.json")],
            install=CommandResult(
                "npm install", str(project := workspace_tmp / "calculator-app"), 0, "", "", True
            ),
            build=CommandResult("npm run build", str(project), 0, "", "", True),
            preview_url="http://127.0.0.1:5173",
            build_passed=True,
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
    assert mission.final_report.get("deployment_status") == "approval required"


def test_deployment_approval_gated(workspace_tmp: Path) -> None:
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
    with patch("nova_core.agent_os.mission.build_calculator_app") as mock_build:
        from nova_core.orchestration.app_builder import BuildResult, CommandResult

        project = workspace_tmp / "calculator-app"
        mock_build.return_value = BuildResult(
            project_path=str(project),
            files_written=[],
            install=CommandResult("npm install", str(project), 0, "", "", True),
            build=CommandResult("npm run build", str(project), 0, "", "", True),
            preview_url="http://127.0.0.1:5173",
            build_passed=True,
        )
        resp = await svc.handle_message(
            message="build a calculator app, test it, preview it, and prepare deployment",
            principal=principal,
        )
    assert resp["intent"] == "agent_os_mission"
    assert resp["intent"] != "general"
    assert "Prime" in resp["response"]


@pytest.fixture
def memory_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    (home / "Documents" / "lund.txt").write_text("lund", encoding="utf-8")
    return home
