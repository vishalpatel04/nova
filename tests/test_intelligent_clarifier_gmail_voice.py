"""Tests for Qwen clarifier, Gmail Orbit, and voice pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.chat import ChatService
from apps.api.services.gmail_oauth_service import GmailOAuthService
from apps.api.services.orbit_email_service import OrbitEmailService
from nova_core.auth.principal import Principal
from nova_core.orbit.email_intent import (
    resolve_email_send_intent,
)
from nova_core.orchestration.app_request import parse_app_request
from nova_core.orchestration.qwen_clarifier import (
    ClarificationPlan,
    deterministic_plan,
    format_clarification_message,
    generate_clarification_plan,
    should_quick_confirm,
)
from nova_core.providers.router import ProviderName
from nova_core.providers.runtime import InferenceResult
from nova_core.schemas.settings import Settings
from nova_core.voice.pipeline import route_voice_transcript
from nova_core.voice.wake_word import parse_wake_command, requires_explicit_voice_approval


def _principal(settings: Settings) -> Principal:
    return Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )


def test_qwen_clarifier_schema_valid_for_vague_landing() -> None:
    request = parse_app_request("build a landing page for SusCo")
    assert request is not None
    plan = deterministic_plan(request)
    validated = ClarificationPlan.model_validate(plan.model_dump())
    assert len(validated.questions) >= 2
    message = format_clarification_message(request, validated)
    assert "use your best assumptions" in message.lower()


@pytest.mark.asyncio
async def test_invalid_qwen_output_falls_back(test_settings: Settings) -> None:
    request = parse_app_request("build a landing page for SusCo")
    assert request is not None
    bad = InferenceResult(
        provider=ProviderName.QWEN,
        model="qwen2.5:7b",
        content="not json",
        mode="local",
        input_tokens=1,
        output_tokens=1,
    )

    with patch(
        "nova_core.orchestration.qwen_clarifier.ProviderRuntime.infer",
        new=AsyncMock(return_value=bad),
    ):
        plan = await generate_clarification_plan(test_settings, request)
    assert len(plan.questions) >= 2


def test_named_todo_quick_confirm() -> None:
    request = parse_app_request("build a todo app called mytasks")
    assert request is not None
    assert should_quick_confirm(request)
    plan = deterministic_plan(request)
    assert plan.proceed_with_confirmation


@pytest.mark.asyncio
async def test_qwen_valid_json_used(test_settings: Settings) -> None:
    request = parse_app_request("build a landing page for SusCo")
    assert request is not None
    payload = {
        "app_type": "landing_page",
        "inferred_goal": "sustainability shopping",
        "inferred_audience": "online shoppers",
        "inferred_style": "premium green",
        "inferred_features": ["hero", "cta"],
        "missing_critical_fields": ["cta"],
        "questions": [
            "Who is the target user?",
            "Investor or consumer tone?",
        ],
        "safe_assumptions": ["CTA: Shop sustainably"],
        "proceed_with_confirmation": False,
        "confirmation_message": "",
        "opening_line": "I can build that. I'm assuming SusCo is a sustainability app.",
    }
    good = InferenceResult(
        provider=ProviderName.QWEN,
        model="qwen2.5:7b",
        content=json.dumps(payload),
        mode="local",
        input_tokens=1,
        output_tokens=1,
    )
    with patch(
        "nova_core.orchestration.qwen_clarifier.ProviderRuntime.infer",
        new=AsyncMock(return_value=good),
    ):
        plan = await generate_clarification_plan(test_settings, request)
    assert "target user" in plan.questions[0].lower()
    message = format_clarification_message(request, plan)
    assert "sustainability" in message.lower()


@pytest.mark.asyncio
async def test_email_asks_recipient_when_missing(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    svc = ChatService(db_session, test_settings)
    resp = await svc.handle_message(
        message="draft an investor update email about this app",
        principal=_principal(test_settings),
    )
    assert (
        "who should receive" in resp["response"].lower()
        or "email address" in resp["response"].lower()
    )


@pytest.mark.asyncio
async def test_email_edit_not_send(
    db_session: AsyncSession,
    test_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(tmp_path / "ws"))
    svc = ChatService(db_session, test_settings)
    principal = _principal(test_settings)
    first = await svc.handle_message(
        message="draft an email to investor@example.com about this app",
        principal=principal,
    )
    assert first.get("orbit_email_draft") is not None
    edited = await svc.handle_message(
        message="make it shorter",
        principal=principal,
        session_id=first["session_id"],
    )
    assert edited["intent"] == "orbit_email_edit"
    assert edited.get("orbit_email_draft") is not None


def test_gmail_status_no_secrets(test_settings: Settings) -> None:
    status = GmailOAuthService(test_settings).status()
    assert "token_location" in status
    assert "refresh" not in str(status).lower()


def test_send_requires_approval_when_not_awaiting() -> None:
    assert resolve_email_send_intent("yes", awaiting=False) is None


def test_voice_wake_parsing() -> None:
    parsed = parse_wake_command("hey nova build a todo app called voice tasks")
    assert parsed.wake_detected
    assert "todo" in parsed.command.lower()


def test_voice_explicit_send_approval() -> None:
    assert requires_explicit_voice_approval("yes", pending_kind="orbit_email_send")
    assert not requires_explicit_voice_approval("yes, send email", pending_kind="orbit_email_send")


@pytest.mark.asyncio
async def test_voice_transcript_routes_command() -> None:
    command, wake = route_voice_transcript("nova draft an email about this app")
    assert wake == "nova"
    assert "draft" in command.lower()


def test_local_draft_honest_when_gmail_missing(
    test_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(tmp_path / "ws"))
    from nova_core.orbit.email_intent import parse_email_draft_request

    svc = OrbitEmailService(test_settings)
    parsed = parse_email_draft_request("draft an email to investor@example.com about this app")
    assert parsed is not None
    draft = svc.create_draft(parsed)
    assert draft.source == "local"
    assert Path(draft.evidence_path).exists()


def test_intent_debug_no_secrets(test_settings: Settings) -> None:
    from nova_core.orchestration.intent_debug import log_intent_route

    settings = test_settings.model_copy(update={"nova_intent_debug": True})
    # Should not raise; logs route metadata only.
    log_intent_route(
        settings,
        text="secret-token-abc",
        intent="orbit_email_draft",
        handler="orbit_email_draft",
    )
