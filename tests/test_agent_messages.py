"""Agent message tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_agent_messages_in_mission(
    auth_client: AsyncClient, paired_worker_token: tuple[str, str]
) -> None:
    device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": device_id, "status": "online"},
    )
    response = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Agent message test"},
    )
    data = response.json()
    messages = data["agent_messages"]
    assert len(messages) >= 1
    assert messages[0]["agent_id"] == "nova"
    assert messages[0]["role"] == "assistant"
    assert len(messages[0]["content"]) > 0
