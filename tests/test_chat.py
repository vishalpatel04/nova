"""Phase 3A chat endpoint tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.chat import ChatService
from nova_core.auth.principal import Principal
from nova_core.providers.router import ProviderName
from nova_core.providers.runtime import InferenceResult


@pytest.mark.asyncio
async def test_chat_requires_client_auth(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/api/v1/chat", json={"message": "help"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_help_command(auth_client: AsyncClient, paired_client_token) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post("/api/v1/chat", json={"message": "help"})
    assert resp.status_code == 200
    data = resp.json()
    assert "NOVA commands" in data["response"]
    assert "set project" in data["response"]
    assert data["intent"] == "help"
    assert data["blocked"] is False


@pytest.mark.asyncio
async def test_chat_system_status(auth_client: AsyncClient, paired_client_token) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post("/api/v1/chat", json={"message": "system status"})
    assert resp.status_code == 200
    body = resp.json()["response"]
    assert "Workers online" in body or "Control plane" in body


@pytest.mark.asyncio
async def test_chat_connected_devices(auth_client: AsyncClient, paired_client_token) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post("/api/v1/chat", json={"message": "connected devices"})
    assert resp.status_code == 200
    assert "device" in resp.json()["response"].lower()


@pytest.mark.asyncio
async def test_chat_blocks_unsafe_request(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    from sqlalchemy import select

    from nova_core.models.orm import ApprovalRequest, AuditEvent

    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post("/api/v1/chat", json={"message": "run shell rm -rf /"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["blocked"] is True
    assert data.get("approval_required") is not True

    pending = await db_session.execute(select(ApprovalRequest))
    assert pending.scalars().all() == []

    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "chat.action_blocked")
    )
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_chat_blocks_secret_read_path(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    from sqlalchemy import select

    from nova_core.models.orm import AuditEvent

    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post(
        "/api/v1/chat", json={"message": "read file ~/Projects/nova/.env"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["blocked"] is True
    assert data["intent"] == "blocked"
    assert "Blocked:" in data["response"]

    result = await db_session.execute(
        select(AuditEvent)
        .where(AuditEvent.action == "chat.action_blocked")
        .where(AuditEvent.details["reason"].as_string() == "protected_path_block")
    )
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_chat_routing_prefers_rule_based(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post("/api/v1/chat", json={"message": "worker status"})
    routing = resp.json().get("routing")
    assert routing is not None
    assert routing["paid_call_allowed"] is False


@pytest.mark.asyncio
async def test_chat_general_uses_local_provider_and_memory_context(
    db_session: AsyncSession, test_settings
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=test_settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )

    captured: dict[str, str] = {}

    async def fake_infer(request):  # type: ignore[no-untyped-def]
        captured["prompt"] = request.prompt
        return InferenceResult(
            provider=ProviderName.LOCAL,
            model="qwen2.5:7b",
            content="Hello there.",
            mode="local_ollama",
            input_tokens=3,
            output_tokens=2,
        )

    svc._provider_runtime.infer = fake_infer  # type: ignore[method-assign]

    result = await svc.handle_message(message="hi", principal=principal)
    assert result["response"] == "Hello there."
    assert result["selected_provider"] == "local"
    assert result["selected_model"] == "qwen2.5:7b"
    assert result["runtime_mode"] == "local_ollama"
    assert "User: hi" in captured["prompt"]


@pytest.mark.asyncio
async def test_chat_general_falls_back_only_when_provider_unavailable(
    db_session: AsyncSession, test_settings
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=test_settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )

    async def fake_infer(_request):  # type: ignore[no-untyped-def]
        return InferenceResult(
            provider=ProviderName.LOCAL,
            model="rule_based",
            content=svc._provider_runtime._default_help(),
            mode="degraded_rule_based",
            input_tokens=3,
            output_tokens=5,
            fallback_used=True,
            fallback_reason="provider_unreachable",
        )

    svc._provider_runtime.infer = fake_infer  # type: ignore[method-assign]
    result = await svc.handle_message(
        message="do you know manish sainani from hushhh", principal=principal
    )
    assert result["response"] == svc._provider_runtime._default_help()
    assert result["runtime_mode"] == "degraded_rule_based"
    assert result["fallback_reason"] == "provider_unreachable"


@pytest.mark.asyncio
async def test_chat_memory_commands_survive_new_chat(
    db_session: AsyncSession, test_settings
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=test_settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )

    remembered = await svc.handle_message(
        message="remember that my exchange files are usually in Downloads",
        principal=principal,
    )
    assert remembered["intent"] == "remember_memory"
    assert "remembered" in remembered["response"].lower()

    new_chat = await svc.handle_message(
        message="what do you remember about me?", principal=principal
    )
    assert "exchange files" in new_chat["response"].lower()
    assert "downloads" in new_chat["response"].lower()

    lookup = await svc.handle_message(
        message="where are my exchange files usually stored?",
        principal=principal,
    )
    assert lookup["response"] == "Downloads"

    forgot = await svc.handle_message(message="forget exchange files", principal=principal)
    assert forgot["intent"] == "forget_memory"

    after_forget = await svc.handle_message(
        message="where are my exchange files usually stored?",
        principal=principal,
    )
    assert "don't know" in after_forget["response"].lower()


@pytest.mark.asyncio
async def test_chat_stream_and_nonstream_final_content_align(
    db_session: AsyncSession, test_settings
) -> None:
    svc = ChatService(db_session, test_settings)
    principal = Principal(
        principal_type="device",
        principal_id="test-device",
        user_id=test_settings.nova_default_user_id,
        device_id="test-device",
        token_role="client",
    )

    async def fake_infer(_request):  # type: ignore[no-untyped-def]
        return InferenceResult(
            provider=ProviderName.LOCAL,
            model="qwen2.5:7b",
            content="Hello there.",
            mode="local_ollama",
            input_tokens=3,
            output_tokens=2,
        )

    async def fake_stream(_request, *, cancel=None, telemetry=None):  # type: ignore[no-untyped-def]
        if telemetry is not None:
            telemetry.provider = "local"
            telemetry.model = "qwen2.5:7b"
            telemetry.mode = "local_ollama"
        yield "Hello"
        yield " there."

    svc._provider_runtime.infer = fake_infer  # type: ignore[method-assign]
    svc._provider_runtime.stream = fake_stream  # type: ignore[method-assign]

    non_stream = await svc.handle_message(message="hi", principal=principal)
    events = [event async for event in svc.stream_message(message="hi", principal=principal)]
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["response"] == non_stream["response"] == "Hello there."
