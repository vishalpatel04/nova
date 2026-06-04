"""Phase 3C streaming, companion inbox, and scheduler tests."""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.chat import ChatService
from apps.api.services.stream_registry import register, unregister
from nova_core.auth.principal import Principal
from nova_core.models.orm import AuditEvent, CompanionInboxItem
from nova_core.providers.runtime import InferenceRequest, ProviderRuntime
from nova_core.providers.stream_context import StreamCancelToken
from nova_core.schemas.settings import Settings


@pytest.mark.asyncio
async def test_chat_stream_returns_sse_tokens(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    async with auth_client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "help"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk
        assert "event: session" in body
        assert "event: token" in body
        assert "event: done" in body


@pytest.mark.asyncio
async def test_chat_stream_cancel_endpoint(auth_client: AsyncClient, paired_client_token) -> None:
    device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    token_obj = StreamCancelToken()
    register(token_obj, owner_id=device_id)
    try:
        resp = await auth_client.post(f"/api/v1/chat/stream/{token_obj.stream_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] is True
        assert token_obj.cancelled is True
    finally:
        unregister(token_obj.stream_id, owner_id=device_id)

    missing = await auth_client.post("/api/v1/chat/stream/not-a-stream/cancel")
    assert missing.status_code == 200
    assert missing.json()["cancelled"] is False


@pytest.mark.asyncio
async def test_chat_stream_cancel_rejects_other_device(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    token_obj = StreamCancelToken()
    register(token_obj, owner_id="another-device")
    try:
        resp = await auth_client.post(f"/api/v1/chat/stream/{token_obj.stream_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] is False
        assert token_obj.cancelled is False
    finally:
        unregister(token_obj.stream_id, owner_id="another-device")


@pytest.mark.asyncio
async def test_chat_stream_cancel_after_provider_return_is_not_done(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    svc = ChatService(db_session, test_settings)
    cancel_token = StreamCancelToken()

    async def fake_stream(_request: InferenceRequest, *, cancel: StreamCancelToken | None = None):
        yield "partial"
        if cancel:
            cancel.cancel()

    svc._provider_runtime.stream = fake_stream  # type: ignore[method-assign]
    principal = Principal(
        principal_type="device",
        principal_id="stream-device",
        user_id=test_settings.nova_default_user_id,
        device_id="stream-device",
        token_role="client",
    )

    events = [
        event
        async for event in svc.stream_message(
            message="tell me about nova",
            principal=principal,
            cancel=cancel_token,
        )
    ]
    assert events[-1]["event"] == "cancelled"
    assert all(event["event"] != "done" for event in events)


@pytest.mark.asyncio
async def test_provider_stream_fallback_when_cancelled() -> None:
    runtime = ProviderRuntime(Settings())
    cancel_token = StreamCancelToken()
    cancel_token.cancel()
    chunks = []
    async for chunk in runtime.stream(
        InferenceRequest(prompt="hello", stream=True),
        cancel=cancel_token,
    ):
        chunks.append(chunk)
    assert chunks == [] or cancel_token.cancelled


@pytest.mark.asyncio
async def test_provider_stream_word_fallback() -> None:
    runtime = ProviderRuntime(Settings())
    chunks = []
    async for chunk in runtime.stream(InferenceRequest(prompt="hello there", stream=True)):
        chunks.append(chunk)
    assert "".join(chunks)


@pytest.mark.asyncio
async def test_companion_inbox_device_scoped(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    queued = await auth_client.post(
        "/api/v1/companion/prompts",
        json={"message": "Check status", "target_device_id": device_id},
    )
    assert queued.status_code == 202
    assert queued.json()["inbox_item_id"]

    inbox = await auth_client.get(f"/api/v1/companion/inbox?device_id={device_id}")
    assert inbox.status_code == 200
    items = inbox.json()
    assert len(items) == 1
    assert items[0]["message"] == "Check status"
    assert items[0]["status"] == "pending"

    read = await auth_client.post(f"/api/v1/companion/inbox/{items[0]['id']}/read")
    assert read.status_code == 200
    assert read.json()["status"] == "read"

    stored = await db_session.execute(select(CompanionInboxItem))
    assert stored.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_companion_inbox_rejects_revoked_target(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    from nova_core.models.enums import TokenState
    from nova_core.models.orm import Device

    device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    result = await db_session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one()
    device.token_state = TokenState.REVOKED.value
    await db_session.commit()

    resp = await auth_client.post(
        "/api/v1/companion/prompts",
        json={"message": "nope", "target_device_id": device_id},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_latest_chat_session_restore(auth_client: AsyncClient, paired_client_token) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    created = await auth_client.post("/api/v1/chat", json={"message": "system status"})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    latest = await auth_client.get("/api/v1/chat/sessions/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == session_id
    assert len(latest.json()["messages"]) >= 2


@pytest.mark.asyncio
async def test_scheduler_tick_does_not_execute(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    await auth_client.post(
        "/api/v1/automation/schedules",
        json={
            "title": "Evening status",
            "provider": "n8n",
            "action": "status",
            "schedule": "0 18 * * *",
            "payload": {},
        },
    )

    status = await auth_client.get("/api/v1/scheduler/status")
    assert status.status_code == 200
    body = status.json()
    assert body["paused"] is True
    assert body["task_count"] >= 1

    tick = await auth_client.post("/api/v1/scheduler/tick")
    assert tick.status_code == 200
    tick_body = tick.json()
    assert tick_body["executed"] is False
    assert tick_body["paused"] is True

    audits = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "scheduler.tick")
    )
    assert audits.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_stream_cancel_token_async_wait() -> None:
    token = StreamCancelToken()
    task = asyncio.create_task(token.wait_cancelled())
    await asyncio.sleep(0.01)
    assert not task.done()
    token.cancel()
    await asyncio.wait_for(task, timeout=1.0)
