"""Agent registry — loads commanders and specialists from config/agents.yaml."""

from dataclasses import dataclass, field
from typing import Any

from nova_core.schemas.settings import Settings


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    display_name: str
    role: str
    description: str
    colour_token: str | None = None
    icon_token: str | None = None
    voice_profile_id: str | None = None
    model_tier: str | None = None
    status: str = "active"
    allowed_tool_categories: list[str] = field(default_factory=list)
    parent_commander: str | None = None


def load_agent_registry(settings: Settings) -> list[AgentDefinition]:
    data = settings.load_yaml("agents.yaml")
    agents: list[AgentDefinition] = []

    commanders = data.get("commanders", [])
    if not isinstance(commanders, list):
        commanders = []
    for commander in commanders:
        if isinstance(commander, dict):
            agents.append(_parse_agent(commander))

    specialists = data.get("specialists", [])
    if not isinstance(specialists, list):
        specialists = []
    for specialist in specialists:
        if isinstance(specialist, dict):
            agents.append(_parse_agent(specialist, is_specialist=True))

    return agents


def _parse_agent(raw: dict[str, Any], is_specialist: bool = False) -> AgentDefinition:
    return AgentDefinition(
        id=str(raw["id"]),
        display_name=str(raw["display_name"]),
        role=str(raw["role"]),
        description=str(raw.get("description", "")),
        colour_token=raw.get("colour_token"),
        icon_token=raw.get("icon_token"),
        voice_profile_id=raw.get("voice_profile_id"),
        model_tier=raw.get("model_tier"),
        status=str(raw.get("status", "active")),
        allowed_tool_categories=list(raw.get("allowed_tool_categories", [])),
        parent_commander=str(raw["parent_commander"])
        if is_specialist and raw.get("parent_commander")
        else None,
    )


def get_commander(agents: list[AgentDefinition], commander_id: str) -> AgentDefinition | None:
    return next((a for a in agents if a.id == commander_id), None)
