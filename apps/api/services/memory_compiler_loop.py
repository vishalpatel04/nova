"""Background memory compiler tick for all users with settings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.memory.compiler import MemoryCompiler
from nova_core.models.orm import MemoryUserSettings
from nova_core.schemas.settings import Settings


async def memory_compiler_tick(session: AsyncSession, settings: Settings) -> None:
    result = await session.execute(select(MemoryUserSettings.user_id))
    user_ids = [row[0] for row in result.all()]
    if not user_ids:
        return
    compiler = MemoryCompiler(session, settings)
    for user_id in user_ids:
        await compiler.tick(user_id)
