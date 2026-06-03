"""Agent message tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_agent_messages_in_mission(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Agent message test"},
    )
    data = response.json()
    messages = data["agent_messages"]
    assert len(messages) >= 1
    assert messages[0]["agent_id"] == "nova"
    assert messages[0]["role"] == "assistant"
    assert len(messages[0]["content"]) > 0
