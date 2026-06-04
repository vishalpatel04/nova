"""Slice 2A authentication and pairing tests."""

import pytest
from httpx import AsyncClient

from nova_core.auth.tokens import generate_token, hash_token, token_prefix, verify_token


def test_token_hashing() -> None:
    pepper = "test-pepper"
    token = generate_token("client")
    hashed = hash_token(token, pepper)
    assert hashed != token
    assert verify_token(token, pepper, hashed)
    assert not verify_token("wrong", pepper, hashed)


def test_token_prefix() -> None:
    token = generate_token("worker")
    assert token_prefix(token) == token[:16]


@pytest.mark.asyncio
async def test_unauthenticated_mission_rejected(client: AsyncClient) -> None:
    get_settings = __import__("nova_core.schemas.settings", fromlist=["get_settings"]).get_settings
    get_settings.cache_clear()
    import os

    os.environ["NOVA_REQUIRE_DEVICE_TOKEN"] = "true"

    from apps.api.deps import AppState, set_app_state
    from apps.api.main import create_app

    settings = get_settings()
    set_app_state(AppState(settings=settings, redis=None))
    app = create_app()
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/missions",
            json={"mission_type": "system_status", "title": "No auth"},
        )
        assert resp.status_code == 401

    os.environ["NOVA_REQUIRE_DEVICE_TOKEN"] = "false"


@pytest.mark.asyncio
async def test_bootstrap_admin_can_create_pairing_code(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/api/v1/pairing/codes",
        json={"device_type": "macos_worker", "proposed_device_id": "worker-a"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "code" in data
    assert len(data["code"]) == 6


@pytest.mark.asyncio
async def test_pairing_claim_and_approve(auth_client: AsyncClient) -> None:
    create = await auth_client.post(
        "/api/v1/pairing/codes",
        json={"device_type": "iphone_client", "proposed_device_id": "iphone-1"},
    )
    pairing_id = create.json()["pairing_id"]
    code = create.json()["code"]

    claim = await auth_client.post(
        "/api/v1/pairing/claim",
        json={
            "code": code,
            "device_id": "iphone-1",
            "name": "iPhone",
            "device_type": "iphone_client",
        },
    )
    assert claim.status_code == 200
    assert claim.json()["status"] == "pending_approval"

    approve = await auth_client.post(f"/api/v1/pairing/{pairing_id}/approve")
    assert approve.status_code == 200
    assert "token" in approve.json()
    assert approve.json()["token"].startswith("nova_")


@pytest.mark.asyncio
async def test_token_rotation(
    auth_client: AsyncClient, paired_worker_token: tuple[str, str]
) -> None:
    device_id, _old_token = paired_worker_token
    resp = await auth_client.post(f"/api/v1/devices/{device_id}/rotate-token")
    assert resp.status_code == 200
    new_token = resp.json()["token"]
    assert new_token != _old_token


@pytest.mark.asyncio
async def test_token_revocation(
    auth_client: AsyncClient, paired_worker_token: tuple[str, str]
) -> None:
    device_id, token = paired_worker_token
    revoke = await auth_client.post(
        f"/api/v1/devices/{device_id}/revoke",
        json={"reason": "test revoke"},
    )
    assert revoke.status_code == 200

    client_with_revoked = auth_client
    client_with_revoked.headers["Authorization"] = f"Bearer {token}"
    resp = await client_with_revoked.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": device_id, "status": "online"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_mission(
    auth_client: AsyncClient,
    paired_worker_token: tuple[str, str],
    paired_client_token: tuple[str, str],
) -> None:
    worker_device_id, worker_token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {worker_token}"

    hb = await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": worker_device_id, "status": "online", "payload": {}},
    )
    assert hb.status_code == 200

    _client_device_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    mission = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Auth mission"},
    )
    assert mission.status_code == 201
    assert mission.json()["status"] in ("completed", "queued_waiting_for_worker")


@pytest.mark.asyncio
async def test_pairing_code_one_time_use(auth_client: AsyncClient) -> None:
    create = await auth_client.post(
        "/api/v1/pairing/codes",
        json={"device_type": "iphone_client", "proposed_device_id": "iphone-once"},
    )
    code = create.json()["code"]
    pairing_id = create.json()["pairing_id"]

    claim = await auth_client.post(
        "/api/v1/pairing/claim",
        json={
            "code": code,
            "device_id": "iphone-once",
            "name": "iPhone",
            "device_type": "iphone_client",
        },
    )
    assert claim.status_code == 200

    approve = await auth_client.post(f"/api/v1/pairing/{pairing_id}/approve")
    assert approve.status_code == 200

    reuse = await auth_client.post(
        "/api/v1/pairing/claim",
        json={
            "code": code,
            "device_id": "iphone-once-2",
            "name": "Other",
            "device_type": "iphone_client",
        },
    )
    assert reuse.status_code == 409


@pytest.mark.asyncio
async def test_pairing_code_expiration(db_session, test_settings) -> None:
    from datetime import timedelta

    from apps.api.services.pairing import PairingService
    from nova_core.schemas.errors import ValidationError
    from nova_core.utils.time import utc_now

    svc = PairingService(db_session, test_settings)
    pairing, code = await svc.create_pairing_code(
        user_id="user-1",
        device_type="iphone_client",
        proposed_device_id="iphone-exp",
    )
    pairing.expires_at = utc_now() - timedelta(minutes=1)
    await db_session.commit()

    with pytest.raises(ValidationError, match="expired"):
        await svc.claim_pairing_code(
            code=code,
            device_id="iphone-exp",
            name="Expired",
            device_type="iphone_client",
        )


@pytest.mark.asyncio
async def test_pairing_rate_limit(auth_client: AsyncClient) -> None:
    for i in range(11):
        resp = await auth_client.post(
            "/api/v1/pairing/claim",
            json={
                "code": "BADCODE",
                "device_id": "rate-limit-device",
                "name": "Rate",
                "device_type": "iphone_client",
            },
        )
        if i < 10:
            assert resp.status_code in (404, 422)
        else:
            assert resp.status_code == 422
            assert "rate limit" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_websocket_auth_rejects_missing_token(
    client: AsyncClient, db_engine, test_settings
) -> None:
    import os
    from unittest.mock import MagicMock

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from apps.api.auth import authenticate_websocket
    from apps.api.deps import AppState, set_app_state
    from nova_core.schemas.errors import UnauthorizedError

    os.environ["NOVA_REQUIRE_DEVICE_TOKEN"] = "true"
    get_settings = __import__("nova_core.schemas.settings", fromlist=["get_settings"]).get_settings
    get_settings.cache_clear()
    set_app_state(AppState(settings=get_settings(), redis=None))

    websocket = MagicMock()
    websocket.query_params = {}
    websocket.headers = {}

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        with pytest.raises(UnauthorizedError):
            await authenticate_websocket(websocket, session)

    os.environ["NOVA_REQUIRE_DEVICE_TOKEN"] = "false"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_websocket_auth_consumes_valid_ticket_once(
    auth_client: AsyncClient, paired_worker_token, db_engine
) -> None:
    from unittest.mock import MagicMock

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from apps.api.auth import authenticate_websocket

    device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    issued = await auth_client.post("/api/v1/pairing/ws-tickets", json={"scope": "worker"})
    assert issued.status_code == 200
    ticket = issued.json()["ticket"]
    websocket = MagicMock()
    websocket.query_params = {"ticket": ticket}
    websocket.headers = {}

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        principal = await authenticate_websocket(websocket, session)
        assert principal.device_id == device_id
        assert principal.token_role == "worker"
        assert principal.websocket_scope == "worker"
        with pytest.raises(Exception):
            await authenticate_websocket(websocket, session)


@pytest.mark.asyncio
async def test_credential_scopes_are_separate(
    auth_client: AsyncClient,
    paired_worker_token: tuple[str, str],
    paired_client_token: tuple[str, str],
) -> None:
    worker_device_id, worker_token = paired_worker_token
    client_device_id, client_token = paired_client_token

    auth_client.headers["Authorization"] = f"Bearer {worker_token}"
    worker_create = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Worker should not create"},
    )
    assert worker_create.status_code == 401

    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    client_register = await auth_client.post(
        "/api/v1/workers/register",
        json={
            "device_id": client_device_id,
            "name": "Not Worker",
            "device_type": "macos_worker",
            "capabilities": [],
        },
    )
    assert client_register.status_code == 401

    auth_client.headers["Authorization"] = f"Bearer {worker_token}"
    worker_register = await auth_client.post(
        "/api/v1/workers/register",
        json={
            "device_id": worker_device_id,
            "name": "Worker",
            "device_type": "macos_worker",
            "capabilities": [],
        },
    )
    assert worker_register.status_code == 200


@pytest.mark.asyncio
async def test_websocket_ticket_scope_binding(
    auth_client: AsyncClient, paired_worker_token: tuple[str, str]
) -> None:
    _device_id, worker_token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {worker_token}"
    resp = await auth_client.post(
        "/api/v1/pairing/ws-tickets",
        json={"scope": "mission_events", "mission_id": "mission-1"},
    )
    assert resp.status_code == 401
