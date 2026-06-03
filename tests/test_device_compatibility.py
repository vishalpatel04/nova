"""Future device compatibility tests — ensure device types are not hardcoded to M3."""

import pytest
from httpx import AsyncClient

from nova_core.schemas.settings import Settings


def test_device_types_in_config() -> None:
    settings = Settings(nova_config_dir="config")
    data = settings.load_yaml("devices.yaml")
    types = data["device_types"]
    assert "macos_worker" in types
    assert "linux_worker" in types
    assert "cloud_worker" in types
    assert "friend_laptop" in types
    assert "iphone_client" in types
    assert "macos_genie" in types


@pytest.mark.asyncio
async def test_linux_worker_registration(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/workers/register",
        json={
            "device_id": "linux-worker-001",
            "name": "Linux Worker",
            "device_type": "linux_worker",
            "capabilities": ["shell", "filesystem", "ripgrep"],
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cloud_worker_registration(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/workers/register",
        json={
            "device_id": "cloud-worker-001",
            "name": "Cloud Worker",
            "device_type": "cloud_worker",
            "capabilities": ["shell", "filesystem"],
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_friend_laptop_registration(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/workers/register",
        json={
            "device_id": "friend-laptop-001",
            "name": "Friend Laptop",
            "device_type": "friend_laptop",
            "capabilities": ["filesystem", "ripgrep"],
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_device_id_not_hardware_bound(client: AsyncClient) -> None:
    """Device identity is configurable, not tied to specific hardware."""
    for device_id in ["m3-macbook", "m2-recovered", "mac-mini-01", "custom-slug"]:
        response = await client.post(
            "/api/v1/workers/register",
            json={
                "device_id": device_id,
                "name": f"Device {device_id}",
                "device_type": "macos_worker",
                "capabilities": ["filesystem"],
            },
        )
        assert response.status_code == 200
        assert response.json()["device_id"] == device_id
