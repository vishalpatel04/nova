"""Phase 3A chat endpoint tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


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
    assert "Phase 3A commands" in data["response"]
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

    from nova_core.models.orm import AuditEvent

    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post("/api/v1/chat", json={"message": "run shell rm -rf /"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["blocked"] is True
    assert "Blocked:" in data["response"]

    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "chat.action_blocked")
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
