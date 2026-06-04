"""In-memory registry for active chat stream cancellation tokens."""

from __future__ import annotations

from nova_core.providers.stream_context import StreamCancelToken

_active: dict[str, StreamCancelToken] = {}


def register(token: StreamCancelToken) -> None:
    _active[token.stream_id] = token


def unregister(stream_id: str) -> None:
    _active.pop(stream_id, None)


def cancel(stream_id: str) -> bool:
    token = _active.get(stream_id)
    if token is None:
        return False
    token.cancel()
    return True


def get(stream_id: str) -> StreamCancelToken | None:
    return _active.get(stream_id)
