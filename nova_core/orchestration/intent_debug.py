"""Intent routing debug logging (no secrets)."""

from __future__ import annotations

from nova_core.schemas.settings import Settings
from nova_core.sentry.logging import get_logger

logger = get_logger("nova.chat.intent")


def log_intent_route(
    settings: Settings,
    *,
    text: str,
    intent: str,
    handler: str,
    extra: dict[str, str] | None = None,
) -> None:
    if not settings.nova_intent_debug:
        return
    preview = text.replace("\n", " ").strip()[:120]
    payload: dict[str, str] = {
        "intent": intent,
        "handler": handler,
        "text_preview": preview,
    }
    if extra:
        payload.update({key: str(value) for key, value in extra.items()})
    logger.info("intent_route", **payload)
