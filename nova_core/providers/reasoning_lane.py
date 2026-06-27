"""Reasoning/review provider lane selection (local Qwen vs Anthropic)."""

from __future__ import annotations

import re

from nova_core.providers.router import ProviderName
from nova_core.schemas.settings import Settings

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"

_API_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_-]+")


def anthropic_model_name(settings: Settings) -> str:
    return settings.nova_anthropic_model or DEFAULT_ANTHROPIC_MODEL


def sanitize_anthropic_error(message: str, *, api_key: str = "") -> str:
    text = message.strip()
    key = api_key.strip()
    if key and key in text:
        text = text.replace(key, "***")
    text = _API_KEY_RE.sub("***", text)
    return text[:400]


def anthropic_configured(settings: Settings) -> bool:
    return bool(settings.nova_anthropic_enabled and settings.nova_anthropic_api_key.strip())


def anthropic_status_redacted(settings: Settings) -> dict[str, str | bool]:
    key = settings.nova_anthropic_api_key.strip()
    return {
        "enabled": settings.nova_anthropic_enabled,
        "configured": bool(key),
        "api_key": "***" if key else "",
        "model": anthropic_model_name(settings),
        "reasoning_provider": settings.nova_reasoning_provider,
        "review_provider": settings.nova_review_provider,
    }


def resolve_provider_lane(settings: Settings, *, purpose: str = "reasoning") -> ProviderName:
    """Pick Anthropic when explicitly enabled and configured; else local."""
    pref = (
        settings.nova_review_provider if purpose == "review" else settings.nova_reasoning_provider
    ).lower()
    if pref == "local":
        return ProviderName.LOCAL
    if pref == "anthropic" and anthropic_configured(settings):
        return ProviderName.ANTHROPIC
    if pref == "auto" and anthropic_configured(settings):
        return ProviderName.ANTHROPIC
    return ProviderName.LOCAL
