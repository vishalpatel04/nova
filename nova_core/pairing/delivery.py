"""Ephemeral pairing token delivery — never persist plaintext in PostgreSQL."""

from __future__ import annotations

import time
from typing import Any

from nova_core.schemas.errors import ValidationError
from nova_core.schemas.settings import Settings

_LOCAL_DELIVERIES: dict[str, tuple[str, float]] = {}


def _delivery_key(pairing_id: str) -> str:
    return f"nova:pairing:delivery:{pairing_id}"


async def store_delivery_token(
    redis: Any | None,
    pairing_id: str,
    token: str,
    ttl_seconds: int,
    settings: Settings | None = None,
) -> None:
    if redis is not None:
        await redis.set(_delivery_key(pairing_id), token, ex=ttl_seconds)
        return
    _ensure_local_delivery_allowed(settings)
    _LOCAL_DELIVERIES[pairing_id] = (token, time.time() + ttl_seconds)


async def consume_delivery_token(
    redis: Any | None, pairing_id: str, settings: Settings | None = None
) -> str | None:
    if redis is not None:
        key = _delivery_key(pairing_id)
        if hasattr(redis, "getdel"):
            token = await redis.getdel(key)
        else:
            token = await redis.get(key)
            if token is not None:
                await redis.delete(key)
        if token is None:
            return None
        if isinstance(token, bytes):
            return token.decode()
        return str(token)
    _ensure_local_delivery_allowed(settings)
    entry = _LOCAL_DELIVERIES.pop(pairing_id, None)
    if entry is None:
        return None
    token, expires_at = entry
    if time.time() > expires_at:
        return None
    return token


def clear_local_deliveries_for_tests() -> None:
    _LOCAL_DELIVERIES.clear()


def _ensure_local_delivery_allowed(settings: Settings | None) -> None:
    env = settings.nova_env if settings else "development"
    if env not in {"development", "test"}:
        raise ValidationError(
            "Redis is required for pairing token delivery outside development/test"
        )
