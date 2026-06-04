"""Pairing status polling and one-time token retrieval."""

import pytest
from httpx import AsyncClient

from nova_core.pairing.delivery import clear_local_deliveries_for_tests, store_delivery_token
from nova_core.schemas.errors import ValidationError
from nova_core.schemas.settings import Settings


@pytest.fixture(autouse=True)
def _clear_delivery_cache() -> None:
    clear_local_deliveries_for_tests()
    yield
    clear_local_deliveries_for_tests()


async def _claim_pairing(
    client: AsyncClient, *, device_id: str = "iphone-poll", device_type: str = "iphone_client"
) -> tuple[str, str, str]:
    create = await client.post(
        "/api/v1/pairing/codes",
        json={"device_type": device_type, "proposed_device_id": device_id},
    )
    assert create.status_code == 201
    pairing_id = create.json()["pairing_id"]
    code = create.json()["code"]
    claim = await client.post(
        "/api/v1/pairing/claim",
        json={
            "code": code,
            "device_id": device_id,
            "name": "Poll iPhone",
            "device_type": device_type,
        },
    )
    assert claim.status_code == 200
    assert claim.json()["status"] == "pending"
    return pairing_id, code, device_id


@pytest.mark.asyncio
async def test_pairing_status_pending_then_approved(auth_client: AsyncClient) -> None:
    pairing_id, _, device_id = await _claim_pairing(auth_client)

    status = await auth_client.get(f"/api/v1/pairing/{pairing_id}/status")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "pending"
    assert body["token_ready"] is False

    approve = await auth_client.post(f"/api/v1/pairing/{pairing_id}/approve")
    assert approve.status_code == 200
    assert "token" not in approve.json()

    status2 = await auth_client.get(f"/api/v1/pairing/{pairing_id}/status")
    assert status2.json()["status"] == "approved"
    assert status2.json()["token_ready"] is True

    retrieve = await auth_client.post(
        f"/api/v1/pairing/{pairing_id}/token",
        json={"device_id": device_id},
    )
    assert retrieve.status_code == 200
    token = retrieve.json()["token"]
    assert token.startswith("nova_")

    status3 = await auth_client.get(f"/api/v1/pairing/{pairing_id}/status")
    assert status3.json()["status"] == "claimed"
    assert status3.json()["token_ready"] is False

    again = await auth_client.post(
        f"/api/v1/pairing/{pairing_id}/token",
        json={"device_id": device_id},
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_pairing_token_retrieval_wrong_device(auth_client: AsyncClient) -> None:
    pairing_id, _, _device_id = await _claim_pairing(auth_client, device_id="iphone-wrong")
    await auth_client.post(f"/api/v1/pairing/{pairing_id}/approve")
    resp = await auth_client.post(
        f"/api/v1/pairing/{pairing_id}/token",
        json={"device_id": "other-device"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_pairing_rejected_status(auth_client: AsyncClient) -> None:
    pairing_id, _, _ = await _claim_pairing(auth_client, device_id="iphone-reject")
    reject = await auth_client.post(
        f"/api/v1/pairing/{pairing_id}/reject",
        json={"reason": "not trusted"},
    )
    assert reject.status_code == 200
    status = await auth_client.get(f"/api/v1/pairing/{pairing_id}/status")
    assert status.json()["status"] == "rejected"

    retrieve = await auth_client.post(
        f"/api/v1/pairing/{pairing_id}/token",
        json={"device_id": "iphone-reject"},
    )
    assert retrieve.status_code == 422


@pytest.mark.asyncio
async def test_pairing_status_rate_limit(auth_client: AsyncClient) -> None:
    pairing_id, _, _ = await _claim_pairing(auth_client, device_id="iphone-rate-status")
    for _ in range(31):
        resp = await auth_client.get(f"/api/v1/pairing/{pairing_id}/status")
        if resp.status_code == 422:
            assert "rate limit" in resp.json()["error"]["message"].lower()
            return
    pytest.fail("expected status rate limit")


@pytest.mark.asyncio
async def test_local_delivery_fallback_rejected_outside_dev_or_test() -> None:
    settings = Settings(NOVA_ENV="production", NOVA_TOKEN_PEPPER="prod-pepper")
    with pytest.raises(ValidationError, match="Redis is required"):
        await store_delivery_token(None, "pairing-prod", "nova_dev_secret", 60, settings)
