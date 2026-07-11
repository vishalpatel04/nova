"""Investor demo flow: clarification, pacing, Orbit email drafts."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.chat import ChatService
from apps.api.services.orbit_email_service import OrbitEmailService
from nova_core.auth.principal import Principal
from nova_core.orchestration.app_request import parse_app_request
from nova_core.orchestration.app_spec_clarification import (
    is_assumption_continuation,
    is_vague_app_request,
)
from nova_core.schemas.settings import Settings


@pytest.fixture
def workspace_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "nova-workspace"
    root.mkdir()
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(root))
    return root


def _principal(settings: Settings) -> Principal:
    return Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )


def _mock_build_result(workspace_tmp: Path, app_type: str, name: str, dirname: str):
    from nova_core.orchestration.app_builder import BuildResult, CommandResult
    from nova_core.orchestration.preview import PreviewSession

    project = workspace_tmp / dirname
    return BuildResult(
        project_path=str(project),
        files_written=[str(project / "package.json"), str(project / "src" / "App.tsx")],
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


def test_landing_page_request_is_vague() -> None:
    parsed = parse_app_request("build a landing page for SusCo")
    assert parsed is not None
    assert is_vague_app_request(parsed)


def test_named_calculator_is_specific() -> None:
    parsed = parse_app_request("create a calculator app named arth")
    assert parsed is not None
    assert not is_vague_app_request(parsed)


def test_assumption_phrase_detected() -> None:
    assert is_assumption_continuation("use your best assumptions")


@pytest.mark.asyncio
async def test_vague_landing_page_returns_clarification_not_build(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    with (
        patch("nova_core.forge.mission_executor.build_app") as mock_build,
        patch(
            "nova_core.orchestration.qwen_clarifier.generate_clarification_plan",
            new=AsyncMock(
                side_effect=lambda _s, request: __import__(
                    "nova_core.orchestration.qwen_clarifier", fromlist=["deterministic_plan"]
                ).deterministic_plan(request)
            ),
        ),
    ):
        resp = await svc.handle_message(
            message="build a landing page for SusCo",
            principal=_principal(test_settings),
        )
    mock_build.assert_not_called()
    assert resp["intent"] == "agent_os_mission"
    assert "use your best assumptions" in resp["response"].lower()
    assert "save this script as" not in resp["response"].lower()


@pytest.mark.asyncio
async def test_assumption_continuation_builds_mission(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(
            workspace_tmp, "landing_page", "SusCo Landing Page", "landing-page-susco"
        )
        first = await svc.handle_message(
            message="build a landing page for SusCo",
            principal=principal,
        )
        session_id = first["session_id"]
        resp = await svc.handle_message(
            message="use your best assumptions",
            principal=principal,
            session_id=session_id,
        )
    assert resp["intent"] == "agent_os_mission"
    payload = resp.get("agent_os_mission")
    assert payload is not None
    assert "Prime" in str(payload.get("agent_timeline"))
    assert "save this script as" not in resp["response"].lower()


@pytest.mark.asyncio
async def test_specific_calculator_builds_directly(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    with patch("nova_core.forge.mission_executor.build_app") as mock_build:
        mock_build.return_value = _mock_build_result(
            workspace_tmp, "calculator", "arth", "arth-calculator-app"
        )
        resp = await svc.handle_message(
            message="create a calculator app named arth",
            principal=_principal(test_settings),
        )
    assert resp["intent"] == "agent_os_mission"
    assert resp.get("agent_os_mission") is not None
    assert "Deploy this app?" in resp["response"]


@pytest.mark.asyncio
async def test_demo_pacing_does_not_fake_build(monkeypatch: pytest.MonkeyPatch) -> None:
    import nova_core.agent_os.timeline as timeline

    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(timeline.time, "sleep", fake_sleep)
    monkeypatch.setenv("NOVA_DEMO_PACING", "true")
    from nova_core.schemas.settings import get_settings

    get_settings.cache_clear()
    timeline._maybe_demo_pace()
    assert sleeps == [timeline._DEMO_PACE_SECONDS]
    get_settings.cache_clear()


def test_landing_template_includes_brand_copy() -> None:
    from nova_core.orchestration.app_request import AppRequest
    from nova_core.orchestration.app_spec import build_app_spec
    from nova_core.orchestration.templates import TEMPLATES

    req = AppRequest(
        raw_user_request="build a landing page for SusCo",
        app_type="landing_page",
        app_name="SusCo Landing Page",
        features=("hero", "features"),
        style_preference="premium",
        deployment_requested=False,
        requires_clarification=False,
    )
    spec = build_app_spec(req)
    files = TEMPLATES["landing_page_react_vite"].build_files(spec)
    app_tsx = files["src/App.tsx"]
    assert "SusCo" in app_tsx
    assert "Shop sustainably" in app_tsx
    assert "Owner: Wing Aditya Singh" in app_tsx
    assert "Owner: Wing Aditya Singh" in app_tsx


@pytest.mark.asyncio
async def test_email_draft_routes_to_orbit(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    resp = await svc.handle_message(
        message="draft an email to investor@example.com about this app",
        principal=_principal(test_settings),
    )
    assert resp["intent"] == "orbit_email_draft"
    payload = resp.get("orbit_email_draft")
    assert payload is not None
    assert payload["result"]["subject"]
    assert "Send this email?" in resp["response"]
    assert "i don't have access" not in resp["response"].lower()


@pytest.mark.asyncio
async def test_email_draft_without_recipient_asks(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    resp = await svc.handle_message(
        message="draft an investor update email about this app",
        principal=_principal(test_settings),
    )
    assert "email" in resp["response"].lower()
    assert resp.get("orbit_email_draft") is None or "who" in resp["response"].lower()


@pytest.mark.asyncio
async def test_email_send_no_skips(
    db_session: AsyncSession, test_settings: Settings, workspace_tmp: Path
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    await svc.handle_message(
        message="draft an email to investor@example.com about this app",
        principal=principal,
    )
    resp = await svc.handle_message(message="no", principal=principal)
    assert resp["intent"] == "orbit_email_send_no"
    assert "skipped" in resp["response"].lower()


@pytest.mark.asyncio
async def test_local_email_artifact_created(
    test_settings: Settings, workspace_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(workspace_tmp))
    svc = OrbitEmailService(test_settings)
    from nova_core.orbit.email_intent import parse_email_draft_request

    parsed = parse_email_draft_request("draft an email to investor@example.com about this app")
    assert parsed is not None
    outcome = await svc.prepare_draft(parsed)
    assert outcome.draft is not None
    draft = outcome.draft
    assert Path(draft.evidence_path).exists()
    assert draft.source == "local"
