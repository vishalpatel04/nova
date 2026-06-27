"""Forge engine registry."""

from __future__ import annotations

from nova_core.forge.engines.base import ForgeEngine
from nova_core.forge.engines.claude_code import ClaudeCodeEngine
from nova_core.forge.engines.codex_cli import CodexCliEngine
from nova_core.forge.engines.deterministic_template import DeterministicTemplateEngine
from nova_core.forge.engines.openhands import OpenHandsEngine
from nova_core.schemas.settings import Settings


def list_engines(settings: Settings | None = None) -> list[ForgeEngine]:
    settings = settings or Settings()
    return [
        DeterministicTemplateEngine(),
        OpenHandsEngine(settings),
        ClaudeCodeEngine(settings),
        CodexCliEngine(settings),
    ]


def get_engine(engine_id: str, settings: Settings | None = None) -> ForgeEngine | None:
    for engine in list_engines(settings):
        if engine.engine_id == engine_id:
            return engine
    return None


def default_engine_id(settings: Settings | None = None) -> str:
    settings = settings or Settings()
    preferred = getattr(settings, "nova_forge_default_engine", "") or "deterministic_template"
    engine = get_engine(preferred, settings)
    if engine is not None and engine.available():
        return preferred
    return "deterministic_template"
