"""In-memory registry for active chat stream cancellation tokens."""

from __future__ import annotations

from dataclasses import dataclass

from nova_core.providers.stream_context import StreamCancelToken


@dataclass(frozen=True)
class RegisteredStream:
    token: StreamCancelToken
    owner_id: str | None


_active: dict[str, RegisteredStream] = {}


def register(token: StreamCancelToken, *, owner_id: str | None = None) -> None:
    _active[token.stream_id] = RegisteredStream(token=token, owner_id=owner_id)


def unregister(stream_id: str, *, owner_id: str | None = None) -> None:
    registered = _active.get(stream_id)
    if (
        registered is not None
        and registered.owner_id is not None
        and registered.owner_id != owner_id
    ):
        return
    _active.pop(stream_id, None)


def cancel(stream_id: str, *, owner_id: str | None = None) -> bool:
    registered = _active.get(stream_id)
    if registered is None:
        return False
    if registered.owner_id is not None and registered.owner_id != owner_id:
        return False
    registered.token.cancel()
    return True


def get(stream_id: str) -> StreamCancelToken | None:
    registered = _active.get(stream_id)
    return registered.token if registered else None
