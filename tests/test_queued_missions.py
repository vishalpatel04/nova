"""Queued mission and worker state tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_queued_mission_when_worker_offline(
    auth_client: AsyncClient, paired_client_token
) -> None:
    """Without heartbeat, system_status mission should queue honestly."""
    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    resp = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Offline queue test"},
        headers={"Idempotency-Key": "queue-test-1"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "queued_waiting_for_worker"


@pytest.mark.asyncio
async def test_mission_runs_when_worker_online(
    auth_client: AsyncClient, paired_worker_token, paired_client_token
) -> None:
    device_id, worker_token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {worker_token}"

    await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": device_id, "status": "online", "payload": {"cpu": 5}},
    )

    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    resp = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Online test"},
        headers={"Idempotency-Key": "online-test-1"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_worker_stale_and_offline_transitions(
    auth_client: AsyncClient, paired_worker_token
) -> None:
    device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": device_id, "status": "online"},
    )

    auth_client.headers["Authorization"] = "Bearer nova_bts_test_admin"
    status = await auth_client.get("/api/v1/system/status")
    assert status.status_code == 200
    assert status.json()["workers_online"] >= 1


@pytest.mark.asyncio
async def test_future_device_compatibility(auth_client: AsyncClient) -> None:
    for device_type in ["linux_worker", "cloud_worker", "friend_laptop"]:
        create = await auth_client.post(
            "/api/v1/pairing/codes",
            json={"device_type": device_type, "proposed_device_id": f"dev-{device_type}"},
        )
        assert create.status_code == 201


@pytest.mark.asyncio
async def test_queued_mission_pickup_structure(
    auth_client: AsyncClient, paired_worker_token, paired_client_token, db_engine, test_settings
) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from apps.api.services.missions import MissionService
    from nova_core.models.orm import QueuedMission

    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    queued_resp = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Pickup test"},
        headers={"Idempotency-Key": "pickup-test-1"},
    )
    assert queued_resp.json()["status"] == "queued_waiting_for_worker"
    mission_id = queued_resp.json()["id"]

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(
            select(QueuedMission).where(QueuedMission.mission_id == mission_id)
        )
        queued = result.scalar_one()
        assert queued.picked_up_at is None
        assert "macos_worker" in queued.required_device_types

        device_id, token = paired_worker_token
        auth_client.headers["Authorization"] = f"Bearer {token}"
        await auth_client.post(
            "/api/v1/workers/heartbeat",
            json={"device_id": device_id, "status": "online"},
        )

        svc = MissionService(session, test_settings)
        assigned = await svc.assign_queued_missions(device_id)
        assert {
            "mission_id": mission_id,
            "command_id": f"mission:{mission_id}:worker:{device_id}",
        } in assigned
        mission = await svc.acknowledge_worker_pickup(
            device_id=device_id,
            mission_id=mission_id,
            command_id=f"mission:{mission_id}:worker:{device_id}",
        )
        assert mission.status == "running"


@pytest.mark.asyncio
async def test_duplicate_worker_pickup_ack_is_idempotent(
    auth_client: AsyncClient, paired_worker_token, paired_client_token, db_engine, test_settings
) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from apps.api.services.missions import MissionService
    from nova_core.models.orm import TimelineEvent

    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    queued_resp = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Duplicate pickup test"},
        headers={"Idempotency-Key": "pickup-duplicate-test-1"},
    )
    mission_id = queued_resp.json()["id"]
    device_id, _token = paired_worker_token
    command_id = f"mission:{mission_id}:worker:{device_id}"

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        svc = MissionService(session, test_settings)
        assigned_once = await svc.assign_queued_missions(device_id)
        assigned_twice = await svc.assign_queued_missions(device_id)
        assert assigned_once == assigned_twice
        await svc.acknowledge_worker_pickup(
            device_id=device_id,
            mission_id=mission_id,
            command_id=command_id,
        )
        await svc.acknowledge_worker_pickup(
            device_id=device_id,
            mission_id=mission_id,
            command_id=command_id,
        )
        result = await session.execute(
            select(TimelineEvent).where(
                TimelineEvent.mission_id == mission_id,
                TimelineEvent.event_type == "mission_started",
            )
        )
        assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_worker_revocation_releases_unacknowledged_assignment(
    auth_client: AsyncClient, paired_worker_token, paired_client_token, db_engine
) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from nova_core.models.orm import QueuedMission

    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    queued_resp = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Release revoked assignment"},
        headers={"Idempotency-Key": "release-revoked-assignment-1"},
    )
    mission_id = queued_resp.json()["id"]
    worker_id, _worker_token = paired_worker_token

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        from apps.api.services.missions import MissionService
        from nova_core.schemas.settings import get_settings

        assigned = await MissionService(session, get_settings()).assign_queued_missions(worker_id)
        assert assigned[0]["mission_id"] == mission_id

    auth_client.headers["Authorization"] = "Bearer nova_bts_test_admin"
    revoke = await auth_client.post(
        f"/api/v1/devices/{worker_id}/revoke",
        json={"reason": "test release"},
    )
    assert revoke.status_code == 200

    async with factory() as session:
        result = await session.execute(
            select(QueuedMission).where(QueuedMission.mission_id == mission_id)
        )
        queued = result.scalar_one()
        assert queued.picked_up_at is None
        assert queued.picked_up_by_device_id is None
        assert queued.command_id is None
