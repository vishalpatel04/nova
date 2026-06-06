"""Future device compatibility tests — ensure device types are not hardcoded to M3."""

import pytest
from httpx import AsyncClient

from nova_core.schemas.settings import Settings


def test_device_types_in_config() -> None:
    settings = Settings(nova_config_dir="config", _env_file=None)
    data = settings.load_yaml("devices.yaml")
    types = data["device_types"]
    assert "macos_worker" in types
    assert "linux_worker" in types
    assert "cloud_worker" in types
    assert "friend_laptop" in types
    assert "iphone_client" in types
    assert "macos_genie" in types


@pytest.mark.asyncio
async def test_linux_worker_pairing(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/api/v1/pairing/codes",
        json={"device_type": "linux_worker", "proposed_device_id": "linux-worker-001"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_cloud_worker_pairing(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/api/v1/pairing/codes",
        json={"device_type": "cloud_worker", "proposed_device_id": "cloud-worker-001"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_friend_laptop_pairing(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/api/v1/pairing/codes",
        json={"device_type": "friend_laptop", "proposed_device_id": "friend-laptop-001"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_device_id_not_hardware_bound(auth_client: AsyncClient) -> None:
    """Device identity is configurable, not tied to specific hardware."""
    for device_id in ["m3-macbook", "m2-recovered", "mac-mini-01", "custom-slug"]:
        resp = await auth_client.post(
            "/api/v1/pairing/codes",
            json={"device_type": "macos_worker", "proposed_device_id": device_id},
        )
        assert resp.status_code == 201
        assert resp.json()["pairing_id"]
