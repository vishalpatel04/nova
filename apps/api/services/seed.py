"""Seed agents from config into database."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.agents.registry import load_agent_registry
from nova_core.models.orm import Agent
from nova_core.schemas.settings import Settings


async def seed_agents(session: AsyncSession, settings: Settings) -> int:
    registry = load_agent_registry(settings)
    count = 0

    for agent_def in registry:
        result = await session.execute(select(Agent).where(Agent.id == agent_def.id))
        existing = result.scalar_one_or_none()

        if existing:
            existing.display_name = agent_def.display_name
            existing.role = agent_def.role
            existing.description = agent_def.description
            existing.colour_token = agent_def.colour_token
            existing.icon_token = agent_def.icon_token
            existing.voice_profile_id = agent_def.voice_profile_id
            existing.model_tier = agent_def.model_tier
            existing.status = agent_def.status
            existing.allowed_tool_categories = agent_def.allowed_tool_categories
            existing.parent_agent_id = agent_def.parent_commander
        else:
            session.add(
                Agent(
                    id=agent_def.id,
                    display_name=agent_def.display_name,
                    role=agent_def.role,
                    description=agent_def.description,
                    colour_token=agent_def.colour_token,
                    icon_token=agent_def.icon_token,
                    voice_profile_id=agent_def.voice_profile_id,
                    model_tier=agent_def.model_tier,
                    status=agent_def.status,
                    parent_agent_id=agent_def.parent_commander,
                    allowed_tool_categories=agent_def.allowed_tool_categories,
                )
            )
        count += 1

    await session.commit()
    return count
