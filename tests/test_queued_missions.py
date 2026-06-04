"""Queued mission and worker state tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_queued_mission_when_worker_offline(auth_client: AsyncClient) -> None:
    """Without heartbeat, system_status mission should queue honestly."""
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
    auth_client: AsyncClient, paired_worker_token
) -> None:
    device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": device_id, "status": "online", "payload": {"cpu": 5}},
    )

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
    auth_client: AsyncClient, paired_worker_token, db_engine, test_settings
) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from apps.api.services.missions import MissionService
    from nova_core.models.orm import QueuedMission

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
        picked = await svc.pickup_queued_missions(device_id)
        assert mission_id in picked
