"""Streaming cancellation and telemetry helpers."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamCancelToken:
    stream_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    async def wait_cancelled(self) -> None:
        await self._event.wait()


@dataclass
class StreamTelemetry:
    stream_id: str
    provider: str | None = None
    model: str | None = None
    token_count: int = 0
    fallback_used: bool = False
    fallback_reason: str | None = None
    cancelled: bool = False
    error: str | None = None
    mode: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "provider": self.provider,
            "model": self.model,
            "token_count": self.token_count,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "cancelled": self.cancelled,
            "error": self.error,
            "mode": self.mode,
        }
