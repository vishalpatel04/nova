"""Worker registration and heartbeat tests."""

import pytest
from httpx import AsyncClient

from apps.worker.main import WorkerDaemon
from apps.worker.ws_client import WorkerWebSocketClient
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
async def test_worker_websocket_url_uses_one_time_ticket(monkeypatch) -> None:
    settings = WorkerSettings(
        CONTROL_PLANE_URL="https://nova.example.test",
        WORKER_TOKEN="nova_wrk_test",
    )
    client = WorkerWebSocketClient(settings, "worker-1", "Worker 1")

    async def fake_ticket() -> str:
        return "ticket-test"

    monkeypatch.setattr(client, "_fetch_ws_ticket", fake_ticket)

    assert await client.ws_url == "wss://nova.example.test/api/v1/ws/worker?ticket=ticket-test"


@pytest.mark.asyncio
async def test_worker_fetches_ticket_from_pairing_route(monkeypatch) -> None:
    requested: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, str]:
            return {"ticket": "ticket-test"}

    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            requested["timeout"] = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            pass

        async def post(
            self, url: str, *, headers: dict[str, str], json: dict[str, str]
        ) -> FakeResponse:
            requested["url"] = url
            requested["headers"] = headers
            requested["json"] = json
            return FakeResponse()

    monkeypatch.setattr("apps.worker.ws_client.httpx.AsyncClient", FakeAsyncClient)
    settings = WorkerSettings(
        CONTROL_PLANE_URL="https://nova.example.test",
        WORKER_TOKEN="nova_wrk_test",
    )

    ticket = await WorkerWebSocketClient(settings, "worker-1", "Worker 1")._fetch_ws_ticket()

    assert ticket == "ticket-test"
    assert requested["url"] == "https://nova.example.test/api/v1/pairing/ws-tickets"
    assert requested["headers"] == {"Authorization": "Bearer nova_wrk_test"}
    assert requested["json"] == {"scope": "worker"}


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
async def test_heartbeat_unknown_device(auth_client: AsyncClient, paired_worker_token) -> None:
    _device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    response = await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": "nonexistent-device", "status": "online"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_devices_list(
    auth_client: AsyncClient, paired_worker_token, paired_client_token
) -> None:
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

    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    response = await auth_client.get("/api/v1/devices")
    assert response.status_code == 200
    devices = response.json()
    assert len(devices) >= 1
    worker = next(d for d in devices if d["id"] == device_id)
    assert "git" in worker["capabilities"]
