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
    return Settings(
        nova_env="test",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://localhost:6379/0",
        nova_config_dir="config",
    )


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
async def client(test_settings: Settings, db_engine) -> AsyncGenerator[AsyncClient, None]:
    from nova_core.models import database as db_module

    get_settings.cache_clear()
    db_module._engine = db_engine
    db_module._session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    set_app_state(AppState(settings=get_settings(), redis=None))

    app = create_app()

    async with db_module._session_factory() as session:
        await seed_agents(session, get_settings())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    db_module._engine = None
    db_module._session_factory = None
    get_settings.cache_clear()
