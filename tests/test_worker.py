"""Worker registration and heartbeat tests."""

import pytest
from httpx import AsyncClient

from apps.worker.main import WorkerDaemon
from nova_core.schemas.settings import WorkerSettings


def test_generated_worker_device_id_is_stable() -> None:
    worker = WorkerDaemon(WorkerSettings(DEVICE_ID="", DEVICE_NAME="Test Worker"))

    first = worker.device_id
    second = worker.device_id

    assert first.startswith("worker-")
    assert second == first


def test_configured_worker_device_id_is_used() -> None:
    worker = WorkerDaemon(WorkerSettings(DEVICE_ID="configured-worker", DEVICE_NAME="Test Worker"))

    assert worker.device_id == "configured-worker"


@pytest.mark.asyncio
async def test_worker_registration(auth_client: AsyncClient, paired_worker_token) -> None:
    device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    response = await auth_client.post(
        "/api/v1/workers/register",
        json={
            "device_id": device_id,
            "name": "Test Worker",
            "device_type": "macos_worker",
            "hostname": "test-mac.local",
            "os_version": "macOS 15.0",
            "capabilities": ["filesystem", "ripgrep", "git"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == device_id
    assert data["status"] == "registered"


@pytest.mark.asyncio
async def test_worker_heartbeat(auth_client: AsyncClient, paired_worker_token) -> None:
    device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    response = await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={
            "device_id": device_id,
            "status": "online",
            "payload": {"cpu": 10, "memory": 50},
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_heartbeat_unknown_device(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": "nonexistent-device", "status": "online"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_devices_list(auth_client: AsyncClient, paired_worker_token) -> None:
    device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    await auth_client.post(
        "/api/v1/workers/register",
        json={
            "device_id": device_id,
            "name": "List Test",
            "device_type": "macos_worker",
            "capabilities": ["git"],
        },
    )

    response = await auth_client.get("/api/v1/devices")
    assert response.status_code == 200
    devices = response.json()
    assert len(devices) >= 1
    worker = next(d for d in devices if d["id"] == device_id)
    assert "git" in worker["capabilities"]
