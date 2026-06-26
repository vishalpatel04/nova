"""Tests for pending tool intent memory and multi-turn personal search."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.pending_tool_intents import PendingToolIntentService
from apps.api.services.projects import ProjectService
from nova_core.auth.principal import Principal
from nova_core.models.enums import PendingToolIntentStatus
from nova_core.models.orm import PendingToolIntent
from nova_core.tools.pending_search import parse_scope_confirmation_reply


@pytest.fixture
def allow_demo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "demo-proj"
    root.mkdir()
    (root / "README.md").write_text("# Demo", encoding="utf-8")

    def _fake_roots(roots: list[str] | None = None) -> list[Path]:
        return [root.resolve()]

    monkeypatch.setattr("nova_core.tools.safe_paths.expand_allowed_roots", _fake_roots)
    monkeypatch.setattr("nova_core.project.context.expand_allowed_roots", _fake_roots)
    return root.resolve()


@pytest.fixture
def personal_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    for name in ("Projects", "Desktop", "Documents", "Downloads"):
        (home / name).mkdir(parents=True)
    (home / "Downloads" / "notes.txt").write_text("lund university notes", encoding="utf-8")
    (home / "Documents" / "report.txt").write_text("annual lund report", encoding="utf-8")
    return home


def _patch_search_roots(monkeypatch: pytest.MonkeyPatch, personal_home: Path) -> None:
    monkeypatch.setenv("HOME", str(personal_home))
    roots = [
        str(personal_home / name) for name in ("Projects", "Desktop", "Documents", "Downloads")
    ]

    def _fake_search_roots(configured: list[str] | None = None) -> list[Path]:
        del configured
        return [Path(r).resolve() for r in roots]

    monkeypatch.setattr("nova_core.tools.search_scopes.expand_search_roots", _fake_search_roots)


def _infer_result() -> object:
    from nova_core.providers.router import ProviderName
    from nova_core.providers.runtime import InferenceResult

    return InferenceResult(
        provider=ProviderName.LOCAL,
        model="test",
        content="general reply",
        mode="local",
        input_tokens=1,
        output_tokens=1,
    )


async def _chat(
    auth_client: AsyncClient,
    token: str,
    message: str,
    *,
    session_id: str | None = None,
) -> dict:
    auth_client.headers["Authorization"] = f"Bearer {token}"
    payload: dict[str, str] = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    resp = await auth_client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _seed_pending_computer_search(
    auth_client: AsyncClient,
    token: str,
    db_session: AsyncSession,
    device_id: str,
    *,
    query: str = "lund",
    user_id: str = "arth",
) -> str:
    body = await _chat(auth_client, token, "help")
    session_id = body["session_id"]
    principal = Principal(
        principal_type="device",
        principal_id=device_id,
        user_id=user_id,
        device_id=device_id,
        token_role="client",
    )
    svc = PendingToolIntentService(db_session)
    await svc.create_scope_confirmation(principal, session_id=session_id, query=query)
    await db_session.flush()
    return session_id


@pytest.mark.asyncio
async def test_broad_search_routes_to_archive(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    db_session: AsyncSession,
) -> None:
    _device_id, token = paired_client_token
    body = await _chat(auth_client, token, "search my computer for lund")
    assert body["intent"] == "archive_search"
    assert body.get("pending_tool_intent") is None
    assert "File Explorer" not in body["response"]
    assert "don't have direct access" not in body["response"].lower()

    result = await db_session.execute(select(PendingToolIntent))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_downloads_follow_up_executes_downloads_search(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    personal_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    _patch_search_roots(monkeypatch, personal_home)
    device_id, token = paired_client_token
    session_id = await _seed_pending_computer_search(auth_client, token, db_session, device_id)
    second = await _chat(auth_client, token, "Downloads", session_id=session_id)
    assert second["intent"] == "safe_search"
    assert "Found" in second["response"] or "0 matches" in second["response"]
    assert "No active project" not in second["response"]


@pytest.mark.asyncio
async def test_yes_executes_all_approved_search(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    personal_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    _patch_search_roots(monkeypatch, personal_home)
    device_id, token = paired_client_token
    session_id = await _seed_pending_computer_search(auth_client, token, db_session, device_id)
    second = await _chat(auth_client, token, "yes", session_id=session_id)
    assert second["intent"] == "safe_search"
    assert "Found" in second["response"]


@pytest.mark.asyncio
async def test_no_cancels_pending_intent(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    db_session: AsyncSession,
) -> None:
    device_id, token = paired_client_token
    session_id = await _seed_pending_computer_search(auth_client, token, db_session, device_id)
    second = await _chat(auth_client, token, "no", session_id=session_id)
    assert second["intent"] == "pending_cancelled"
    assert "Search cancelled." in second["response"]

    result = await db_session.execute(
        select(PendingToolIntent).where(PendingToolIntent.device_id == device_id)
    )
    record = result.scalar_one()
    assert record.status == PendingToolIntentStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_pending_intent_expires(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    db_session: AsyncSession,
) -> None:
    device_id, token = paired_client_token
    session_id = await _seed_pending_computer_search(auth_client, token, db_session, device_id)
    result = await db_session.execute(
        select(PendingToolIntent).where(PendingToolIntent.session_id == session_id)
    )
    record = result.scalar_one()
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.flush()

    second = await _chat(auth_client, token, "Downloads", session_id=session_id)
    assert second["intent"] == "pending_expired"
    assert "expired" in second["response"].lower()


@pytest.mark.asyncio
async def test_pending_intent_is_device_scoped(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    db_session: AsyncSession,
    test_settings,
) -> None:
    device_id, token = paired_client_token
    session_id = await _seed_pending_computer_search(auth_client, token, db_session, device_id)

    other = Principal(
        principal_type="device",
        principal_id="other-device",
        user_id="arth",
        device_id="other-device",
    )
    svc = PendingToolIntentService(db_session)
    active = await svc.get_active(other, session_id)
    assert active is None

    active_owner = await svc.get_active(
        Principal(
            principal_type="device",
            principal_id=device_id,
            user_id="arth",
            device_id=device_id,
        ),
        session_id,
    )
    assert active_owner is not None


@pytest.mark.asyncio
async def test_pending_intent_is_session_scoped(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    db_session: AsyncSession,
) -> None:
    _device_id, token = paired_client_token
    await _seed_pending_computer_search(auth_client, token, db_session, _device_id)
    other_session = await _chat(auth_client, token, "help")
    with patch(
        "apps.api.services.chat.ProviderRuntime.infer",
        new_callable=AsyncMock,
        return_value=_infer_result(),
    ) as infer_mock:
        third = await _chat(auth_client, token, "Downloads", session_id=other_session["session_id"])
        infer_mock.assert_called_once()
    assert third["intent"] != "safe_search"


@pytest.mark.asyncio
async def test_replay_follow_up_does_not_execute_twice(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    personal_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    _patch_search_roots(monkeypatch, personal_home)
    device_id, token = paired_client_token
    session_id = await _seed_pending_computer_search(auth_client, token, db_session, device_id)
    second = await _chat(auth_client, token, "Downloads", session_id=session_id)
    assert second["intent"] == "safe_search"
    third = await _chat(auth_client, token, "Downloads", session_id=session_id)
    assert third["intent"] != "safe_search" or "Found" not in third["response"]

    result = await db_session.execute(
        select(PendingToolIntent).where(PendingToolIntent.device_id == device_id)
    )
    record = result.scalar_one()
    assert record.status == PendingToolIntentStatus.CONSUMED.value


@pytest.mark.asyncio
async def test_personal_folder_search_without_active_project(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    personal_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_search_roots(monkeypatch, personal_home)
    _device_id, token = paired_client_token
    resp = await _chat(
        auth_client,
        token,
        f"search Assignment in {personal_home / 'Downloads'}",
    )
    assert "No active project" not in resp["response"]
    assert resp["intent"] in {"safe_search", "blocked"}


@pytest.mark.asyncio
async def test_case_insensitive_search_in_path(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    personal_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_search_roots(monkeypatch, personal_home)
    _device_id, token = paired_client_token
    resp = await _chat(
        auth_client,
        token,
        f"search Assignment In {personal_home / 'Downloads'}",
    )
    assert resp["intent"] == "safe_search"
    assert "No active project" not in resp["response"]


@pytest.mark.asyncio
async def test_plain_project_search_requires_active_project(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
) -> None:
    _device_id, token = paired_client_token
    resp = await _chat(auth_client, token, "search lund")
    assert "No active project" in resp["response"]


@pytest.mark.asyncio
async def test_protected_scope_remains_blocked_on_follow_up(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    db_session: AsyncSession,
) -> None:
    _device_id, token = paired_client_token
    session_id = await _seed_pending_computer_search(auth_client, token, db_session, _device_id)
    second = await _chat(
        auth_client,
        token,
        "~/NOVA_VAULT",
        session_id=session_id,
    )
    assert second["blocked"] is True or "protected" in second["response"].lower()


@pytest.mark.asyncio
async def test_ollama_not_called_for_folder_choice_reply(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    personal_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    _patch_search_roots(monkeypatch, personal_home)
    device_id, token = paired_client_token
    session_id = await _seed_pending_computer_search(auth_client, token, db_session, device_id)
    with patch(
        "apps.api.services.chat.ProviderRuntime.infer",
        new_callable=AsyncMock,
        return_value=_infer_result(),
    ) as infer_mock:
        await _chat(auth_client, token, "Downloads", session_id=session_id)
        infer_mock.assert_not_called()


@pytest.mark.asyncio
async def test_unrelated_message_prompts_without_ollama(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    db_session: AsyncSession,
) -> None:
    device_id, token = paired_client_token
    session_id = await _seed_pending_computer_search(auth_client, token, db_session, device_id)
    with patch(
        "apps.api.services.chat.ProviderRuntime.infer",
        new_callable=AsyncMock,
        return_value=_infer_result(),
    ) as infer_mock:
        second = await _chat(auth_client, token, "hello there", session_id=session_id)
        infer_mock.assert_not_called()
        assert second["intent"] == "pending_scope_confirmation"
        assert second.get("pending_tool_intent")


@pytest.mark.asyncio
async def test_stale_demo_project_cleared(
    db_session: AsyncSession,
    test_settings,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    device_id, _ = paired_client_token
    principal = Principal(
        principal_type="device",
        principal_id=device_id,
        user_id="arth",
        device_id=device_id,
    )
    svc = ProjectService(db_session, test_settings)
    await svc.set_active_project(principal, str(allow_demo_root))
    import shutil

    shutil.rmtree(allow_demo_root)
    assert await svc.get_active_project_or_none(principal) is None


@pytest.mark.asyncio
async def test_valid_stored_project_persists(
    db_session: AsyncSession,
    test_settings,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    device_id, _ = paired_client_token
    principal = Principal(
        principal_type="device",
        principal_id=device_id,
        user_id="arth",
        device_id=device_id,
    )
    svc = ProjectService(db_session, test_settings)
    record = await svc.set_active_project(principal, str(allow_demo_root))
    again = await svc.get_active_project_or_none(principal)
    assert again is not None
    assert again.project_name == record.project_name


def test_parse_scope_confirmation_replies() -> None:
    assert parse_scope_confirmation_reply("Downloads").action == "scope_path"
    assert parse_scope_confirmation_reply("all approved folders").action == "all_approved"
    assert parse_scope_confirmation_reply("yes").action == "all_approved"
    assert parse_scope_confirmation_reply("no").action == "cancel"
    assert parse_scope_confirmation_reply("cancel").action == "cancel"
    assert parse_scope_confirmation_reply("hello").action == "unrelated"


def test_demo_helpers_restore_present() -> None:
    text = Path("scripts/demo_project_helpers.sh").read_text(encoding="utf-8")
    assert "demo_save_active_project" in text
    assert "demo_restore_active_project" in text
