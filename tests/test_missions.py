"""Mission and workflow tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_app_state
from apps.api.routes import _publish_mission_event
from apps.api.services.missions import MissionService
from apps.api.services.seed import seed_agents
from nova_core.models.enums import MissionStatus, TimelineEventType
from nova_core.schemas.settings import Settings
from nova_core.workflows.base import BaseWorkflow, WorkflowContext, WorkflowStepDefinition
from nova_core.workflows.system_status import WORKFLOW_REGISTRY


class FailingWorkflow(BaseWorkflow):
    mission_type = "failing_test"

    def steps(self) -> list[WorkflowStepDefinition]:
        return [
            WorkflowStepDefinition(
                name="fail_intentionally",
                agent_id="nova",
                handler=self._fail,
            )
        ]

    async def _fail(self, _ctx: WorkflowContext) -> dict[str, object]:
        raise RuntimeError("intentional failure")


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


@pytest.mark.asyncio
async def test_failed_mission_records_mission_failed_event(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    await seed_agents(db_session, test_settings)
    WORKFLOW_REGISTRY[FailingWorkflow.mission_type] = FailingWorkflow
    svc = MissionService(db_session, test_settings)

    try:
        mission = await svc.create_mission(
            user_id="arth",
            mission_type=FailingWorkflow.mission_type,
            title="Failure event test",
        )
        with pytest.raises(RuntimeError, match="intentional failure"):
            await svc.execute_mission(mission.id)

        full = await svc.get_mission(mission.id)
        event_types = {e.event_type for e in full.timeline_events}

        assert full.status == MissionStatus.FAILED.value
        assert full.error_message == "intentional failure"
        assert TimelineEventType.STEP_FAILED.value in event_types
        assert TimelineEventType.MISSION_FAILED.value in event_types
    finally:
        WORKFLOW_REGISTRY.pop(FailingWorkflow.mission_type, None)


@pytest.mark.asyncio
async def test_mission_event_publisher_notifies_subscribers(client: AsyncClient) -> None:
    received: list[tuple[str, str, dict[str, object] | None]] = []

    async def subscriber(
        event_type: str, mission_id: str, payload: dict[str, object] | None
    ) -> None:
        received.append((event_type, mission_id, payload))

    state = get_app_state()
    state.mission_event_subscribers["mission-123"] = [subscriber]

    await _publish_mission_event("mission_started", "mission-123", {"title": "Status"})

    assert received == [("mission_started", "mission-123", {"title": "Status"})]
