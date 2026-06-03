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
async def test_worker_registration(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/workers/register",
        json={
            "device_id": "test-worker-001",
            "name": "Test Worker",
            "device_type": "macos_worker",
            "hostname": "test-mac.local",
            "os_version": "macOS 15.0",
            "capabilities": ["filesystem", "ripgrep", "git"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == "test-worker-001"
    assert data["status"] == "registered"


@pytest.mark.asyncio
async def test_worker_heartbeat(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/workers/register",
        json={
            "device_id": "test-worker-002",
            "name": "Heartbeat Worker",
            "device_type": "macos_worker",
            "capabilities": ["shell"],
        },
    )

    response = await client.post(
        "/api/v1/workers/heartbeat",
        json={
            "device_id": "test-worker-002",
            "status": "online",
            "payload": {"cpu": 10, "memory": 50},
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_heartbeat_unknown_device(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": "nonexistent-device", "status": "online"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_devices_list(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/workers/register",
        json={
            "device_id": "list-test-worker",
            "name": "List Test",
            "device_type": "macos_worker",
            "capabilities": ["git"],
        },
    )

    response = await client.get("/api/v1/devices")
    assert response.status_code == 200
    devices = response.json()
    assert len(devices) >= 1
    worker = next(d for d in devices if d["id"] == "list-test-worker")
    assert "git" in worker["capabilities"]
