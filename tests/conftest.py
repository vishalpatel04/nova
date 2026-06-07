"""Test configuration and fixtures."""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.deps import AppState, set_app_state
from apps.api.main import create_app
from apps.api.services.seed import seed_agents
from nova_core.models.database import Base
from nova_core.schemas.settings import Settings, get_settings

TEST_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
def test_settings() -> Settings:
    get_settings.cache_clear()
    os.environ["NOVA_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["NOVA_ALLOW_DATABASE_URL_OVERRIDE"] = "1"
    os.environ["NOVA_REQUIRE_DEVICE_TOKEN"] = "false"
    os.environ["NOVA_BOOTSTRAP_ADMIN_ENABLED"] = "true"
    os.environ["NOVA_BOOTSTRAP_ADMIN_TOKEN"] = "nova_bts_test_admin"
    os.environ["NOVA_TOKEN_PEPPER"] = "test-pepper"
    return Settings(
        nova_env="test",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://localhost:6379/0",
        nova_config_dir="config",
        require_device_token=False,
        nova_bootstrap_admin_enabled=True,
        nova_bootstrap_admin_token="nova_bts_test_admin",
        nova_token_pepper="test-pepper",
    )


@pytest_asyncio.fixture
async def fake_redis():
    try:
        from fakeredis.aioredis import FakeRedis

        redis = FakeRedis(decode_responses=True)
        yield redis
        await redis.aclose()
    except ImportError:
        yield None


@pytest_asyncio.fixture
async def db_engine(test_settings: Settings):
    engine = create_async_engine(test_settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(
    test_settings: Settings, db_engine, fake_redis
) -> AsyncGenerator[AsyncClient, None]:
    from nova_core.models import database as db_module

    get_settings.cache_clear()
    db_module._engine = db_engine
    db_module._session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    set_app_state(AppState(settings=get_settings(), redis=fake_redis))

    app = create_app()

    async with db_module._session_factory() as session:
        await seed_agents(session, get_settings())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    db_module._engine = None
    db_module._session_factory = None
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """Client with bootstrap admin token."""
    client.headers["Authorization"] = "Bearer nova_bts_test_admin"
    return client


async def _retrieve_pairing_token(client: AsyncClient, pairing_id: str, device_id: str) -> str:
    retrieve = await client.post(
        f"/api/v1/pairing/{pairing_id}/token",
        json={"device_id": device_id},
    )
    assert retrieve.status_code == 200, retrieve.text
    return retrieve.json()["token"]


@pytest_asyncio.fixture
async def paired_worker_token(auth_client: AsyncClient) -> tuple[str, str]:
    """Create pairing code and claim worker — returns (device_id, token)."""
    import uuid

    device_id = f"test-worker-{uuid.uuid4().hex[:8]}"
    create_resp = await auth_client.post(
        "/api/v1/pairing/codes",
        json={"device_type": "macos_worker", "proposed_device_id": device_id},
    )
    assert create_resp.status_code == 201
    code = create_resp.json()["code"]
    pairing_id = create_resp.json()["pairing_id"]

    claim_resp = await auth_client.post(
        "/api/v1/pairing/claim",
        json={
            "code": code,
            "device_id": device_id,
            "name": "Test Worker",
            "device_type": "macos_worker",
        },
    )
    assert claim_resp.status_code == 200, claim_resp.text
    if claim_resp.json().get("status") in ("pending", "pending_approval"):
        approve_resp = await auth_client.post(f"/api/v1/pairing/{pairing_id}/approve")
        assert approve_resp.status_code == 200
        token = await _retrieve_pairing_token(auth_client, pairing_id, device_id)
        return device_id, token
    return claim_resp.json()["device_id"], claim_resp.json()["token"]


@pytest_asyncio.fixture
async def paired_client_token(auth_client: AsyncClient) -> tuple[str, str]:
    """Create pairing code and claim client — returns (device_id, token)."""
    import uuid

    device_id = f"test-client-{uuid.uuid4().hex[:8]}"
    create_resp = await auth_client.post(
        "/api/v1/pairing/codes",
        json={"device_type": "iphone_client", "proposed_device_id": device_id},
    )
    assert create_resp.status_code == 201
    code = create_resp.json()["code"]
    pairing_id = create_resp.json()["pairing_id"]

    claim_resp = await auth_client.post(
        "/api/v1/pairing/claim",
        json={
            "code": code,
            "device_id": device_id,
            "name": "Test Client",
            "device_type": "iphone_client",
        },
    )
    assert claim_resp.status_code == 200, claim_resp.text
    if claim_resp.json().get("status") in ("pending", "pending_approval"):
        approve_resp = await auth_client.post(f"/api/v1/pairing/{pairing_id}/approve")
        assert approve_resp.status_code == 200
        token = await _retrieve_pairing_token(auth_client, pairing_id, device_id)
        return device_id, token
    return claim_resp.json()["device_id"], claim_resp.json()["token"]
