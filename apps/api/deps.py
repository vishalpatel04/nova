"""Application state and dependency injection."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.schemas.settings import Settings

MissionEventCallback = Callable[[str, str, dict[str, object] | None], Awaitable[None]]


@dataclass
class AppState:
    settings: Settings
    redis: aioredis.Redis | None = None
    mission_event_subscribers: dict[str, list[MissionEventCallback]] = field(default_factory=dict)


_app_state: AppState | None = None


def set_app_state(state: AppState) -> None:
    global _app_state
    _app_state = state


def get_app_state() -> AppState:
    if _app_state is None:
        raise RuntimeError("App state not initialized")
    return _app_state


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    from nova_core.models.database import get_session

    async for session in get_session():
        yield session
