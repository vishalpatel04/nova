"""Redis Streams transport for worker commands."""

import json
from typing import Any, cast

import redis.asyncio as aioredis


def device_stream_key(device_id: str) -> str:
    return f"nova:worker:{device_id}:commands"


def class_stream_key(worker_class: str) -> str:
    return f"nova:worker-class:{worker_class}:commands"


def _decode(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode()
    return value


async def write_command(
    redis: aioredis.Redis,
    stream_key: str,
    *,
    command_id: str,
    command_type: str,
    mission_id: str | None = None,
    payload: dict[str, Any] | None = None,
    max_len: int = 10000,
) -> str | None:
    fields = {
        "command_id": command_id,
        "command_type": command_type,
        "mission_id": mission_id or "",
        "payload": json.dumps(payload or {}),
    }
    try:
        entry_id = await redis.xadd(
            stream_key,
            cast(Any, fields),
            maxlen=max_len,
            approximate=True,
        )
        return _decode(entry_id)
    except Exception:
        return None


async def read_commands(
    redis: aioredis.Redis,
    stream_key: str,
    *,
    after_id: str = "0-0",
    count: int = 100,
) -> list[dict[str, Any]]:
    try:
        entries = await redis.xrange(stream_key, min=after_id, max="+", count=count)
    except Exception:
        return []
    commands: list[dict[str, Any]] = []
    for entry_id, fields in entries or []:
        if fields is None:
            continue
        payload_raw = _decode(fields.get("payload", "{}"))
        commands.append(
            {
                "stream_id": _decode(entry_id),
                "stream_key": stream_key,
                "command_id": _decode(fields.get("command_id")),
                "command_type": _decode(fields.get("command_type")),
                "mission_id": _decode(fields.get("mission_id")) or None,
                "payload": json.loads(payload_raw) if payload_raw else {},
            }
        )
    return commands
