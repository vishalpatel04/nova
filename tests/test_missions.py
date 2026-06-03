"""Mission and workflow tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.missions import MissionService
from apps.api.services.seed import seed_agents
from nova_core.models.enums import MissionStatus, TimelineEventType
from nova_core.schemas.settings import Settings


@pytest.mark.asyncio
async def test_create_system_status_mission(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/missions",
        json={
            "mission_type": "system_status",
            "title": "Check system status",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["mission_type"] == "system_status"
    assert data["status"] == "completed"
    assert len(data["steps"]) == 3
    assert len(data["timeline_events"]) >= 4
    assert len(data["agent_messages"]) >= 2


@pytest.mark.asyncio
async def test_mission_idempotency(client: AsyncClient) -> None:
    headers = {"Idempotency-Key": "test-key-123"}
    r1 = await client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Idempotent test"},
        headers=headers,
    )
    r2 = await client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Idempotent test"},
        headers=headers,
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


@pytest.mark.asyncio
async def test_get_mission_detail(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Detail test"},
    )
    mission_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/missions/{mission_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == mission_id
    assert data["result_payload"] is not None


@pytest.mark.asyncio
async def test_unknown_mission_type(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/missions",
        json={"mission_type": "nonexistent", "title": "Bad type"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_mission_status_transitions(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    await seed_agents(db_session, test_settings)
    svc = MissionService(db_session, test_settings)
    mission = await svc.create_and_run(
        user_id="arth",
        mission_type="system_status",
        title="Status transition test",
    )
    assert mission.status == MissionStatus.COMPLETED.value
    assert mission.completed_at is not None


@pytest.mark.asyncio
async def test_timeline_events_created(db_session: AsyncSession, test_settings: Settings) -> None:
    await seed_agents(db_session, test_settings)
    svc = MissionService(db_session, test_settings)
    mission = await svc.create_and_run(
        user_id="arth",
        mission_type="system_status",
        title="Timeline test",
    )
    full = await svc.get_mission(mission.id)
    event_types = {e.event_type for e in full.timeline_events}
    assert TimelineEventType.MISSION_CREATED.value in event_types
    assert TimelineEventType.MISSION_STARTED.value in event_types
    assert TimelineEventType.MISSION_COMPLETED.value in event_types
