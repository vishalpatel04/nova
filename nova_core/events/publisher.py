"""Mission event publishing — PostgreSQL durable + Redis Streams transport."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.orm import MissionEventSequence, TimelineEvent


def _decode(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode()
    return value


@dataclass
class PublishedEvent:
    event_id: str
    mission_id: str
    sequence_number: int
    event_type: str
    message: str
    payload: dict[str, Any] | None
    stream_id: str | None
    created_at: datetime
    streaming: str  # "live" | "degraded"


def mission_stream_key(mission_id: str) -> str:
    return f"nova:mission:{mission_id}:events"


async def _next_sequence(session: AsyncSession, mission_id: str) -> int:
    result = await session.execute(
        select(MissionEventSequence).where(MissionEventSequence.mission_id == mission_id)
    )
    seq_row = result.scalar_one_or_none()
    if seq_row is None:
        seq_row = MissionEventSequence(mission_id=mission_id, last_sequence=0)
        session.add(seq_row)
        await session.flush()
    seq_row.last_sequence += 1
    await session.flush()
    return seq_row.last_sequence


async def publish_timeline_event(
    session: AsyncSession,
    redis: aioredis.Redis | None,
    *,
    mission_id: str,
    event_type: str,
    agent_id: str | None,
    message: str,
    payload: dict[str, Any] | None = None,
) -> PublishedEvent:
    sequence = await _next_sequence(session, mission_id)
    now = datetime.now(UTC)
    stream_id: str | None = None
    streaming = "degraded"

    event = TimelineEvent(
        mission_id=mission_id,
        event_type=event_type,
        agent_id=agent_id,
        message=message,
        payload=payload,
        sequence_number=sequence,
    )
    session.add(event)
    await session.flush()

    if redis is not None:
        try:
            fields = {
                "event_id": event.id,
                "sequence_number": str(sequence),
                "event_type": event_type,
                "agent_id": agent_id or "",
                "message": message,
                "payload": json.dumps(payload or {}),
                "timestamp": now.isoformat(),
            }
            stream_id_raw = await redis.xadd(
                mission_stream_key(mission_id),
                cast(Any, fields),
            )
            stream_id = _decode(stream_id_raw)
            event.stream_id = stream_id
            streaming = "live"
        except Exception:
            streaming = "degraded"

    return PublishedEvent(
        event_id=event.id,
        mission_id=mission_id,
        sequence_number=sequence,
        event_type=event_type,
        message=message,
        payload=payload,
        stream_id=stream_id,
        created_at=now,
        streaming=streaming,
    )


async def read_stream_events(
    redis: aioredis.Redis,
    mission_id: str,
    *,
    after_sequence: int = 0,
    count: int = 100,
) -> list[dict[str, Any]]:
    key = mission_stream_key(mission_id)
    entries = await redis.xrange(key, min="-", max="+", count=count * 2)
    events: list[dict[str, Any]] = []
    for entry_id, fields in entries or []:
        if fields is None:
            continue
        seq = int(_decode(fields.get("sequence_number", "0")))
        if seq <= after_sequence:
            continue
        payload_raw = _decode(fields.get("payload", "{}"))
        events.append(
            {
                "event_id": _decode(fields.get("event_id")),
                "sequence_number": seq,
                "event_type": _decode(fields.get("event_type")),
                "agent_id": _decode(fields.get("agent_id")) or None,
                "message": _decode(fields.get("message")),
                "payload": json.loads(payload_raw) if payload_raw else {},
                "stream_id": _decode(entry_id),
                "timestamp": _decode(fields.get("timestamp")),
            }
        )
        if len(events) >= count:
            break
    return events
