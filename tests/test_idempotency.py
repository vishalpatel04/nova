"""Scoped idempotency tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_idempotency_returns_same_mission(
    auth_client: AsyncClient, paired_worker_token
) -> None:
    _device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    headers = {"Idempotency-Key": "scoped-key-001"}

    r1 = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Idempotent"},
        headers=headers,
    )
    r2 = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Idempotent"},
        headers=headers,
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


@pytest.mark.asyncio
async def test_conflicting_idempotency_key(auth_client: AsyncClient, paired_worker_token) -> None:
    _device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    headers = {"Idempotency-Key": "conflict-key-001"}

    r1 = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "First body"},
        headers=headers,
    )
    assert r1.status_code == 201

    r2 = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Different body"},
        headers=headers,
    )
    assert r2.status_code == 409
