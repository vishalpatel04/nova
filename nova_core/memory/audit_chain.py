"""Hash-chained local audit events for memory operations."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.orm import MemoryAuditChain


def _hash_payload(payload: dict[str, Any], previous_hash: str) -> str:
    body = json.dumps({"previous": previous_hash, "payload": payload}, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


async def append_memory_audit(
    session: AsyncSession,
    *,
    user_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> MemoryAuditChain:
    from sqlalchemy import select

    result = await session.execute(
        select(MemoryAuditChain)
        .where(MemoryAuditChain.user_id == user_id)
        .order_by(MemoryAuditChain.created_at.desc())
        .limit(1)
    )
    prev = result.scalar_one_or_none()
    previous_hash = prev.current_hash if prev else "genesis"
    sanitized = {k: v for k, v in payload.items() if k not in {"raw_content", "embedding"}}
    current_hash = _hash_payload(sanitized, previous_hash)
    record = MemoryAuditChain(
        user_id=user_id,
        event_type=event_type,
        sanitized_payload_json=sanitized,
        previous_hash=previous_hash,
        current_hash=current_hash,
    )
    session.add(record)
    await session.flush()
    return record


async def verify_audit_chain(session: AsyncSession, user_id: str) -> bool:
    from sqlalchemy import select

    result = await session.execute(
        select(MemoryAuditChain)
        .where(MemoryAuditChain.user_id == user_id)
        .order_by(MemoryAuditChain.created_at.asc())
    )
    records = list(result.scalars().all())
    expected_prev = "genesis"
    for record in records:
        if record.previous_hash != expected_prev:
            return False
        recomputed = _hash_payload(record.sanitized_payload_json or {}, expected_prev)
        if recomputed != record.current_hash:
            return False
        expected_prev = record.current_hash
    return True
