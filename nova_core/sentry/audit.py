"""Audit event helper — records immutable audit trail entries."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.orm import AuditEvent


async def record_audit_event(
    session: AsyncSession,
    *,
    actor_type: str,
    actor_id: str,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    session.add(event)
    await session.flush()
    return event
