"""Project history helpers for local memory kernel."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.orm import MemoryEvent, MemoryFact, MemoryProjectSummary
from nova_core.utils.time import utc_now


async def events_for_project(
    session: AsyncSession,
    user_id: str,
    project_root: str,
    *,
    limit: int = 50,
) -> list[MemoryEvent]:
    result = await session.execute(
        select(MemoryEvent)
        .where(MemoryEvent.user_id == user_id, MemoryEvent.project_root == project_root)
        .order_by(MemoryEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def events_since(
    session: AsyncSession,
    user_id: str,
    *,
    since: datetime,
    project_root: str | None = None,
    limit: int = 30,
) -> list[MemoryEvent]:
    query = select(MemoryEvent).where(
        MemoryEvent.user_id == user_id,
        MemoryEvent.created_at >= since,
    )
    if project_root:
        query = query.where(MemoryEvent.project_root == project_root)
    result = await session.execute(query.order_by(MemoryEvent.created_at.desc()).limit(limit))
    return list(result.scalars().all())


def format_events(events: list[MemoryEvent], *, title: str) -> str:
    if not events:
        return f"{title}\nNo events recorded."
    lines = [title]
    for ev in reversed(events):
        ts = ev.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
        lines.append(f"- [{ts}] {ev.event_type}: {ev.summary}")
    return "\n".join(lines)


async def format_yesterday_summary(
    session: AsyncSession,
    user_id: str,
    project_root: str | None = None,
) -> str:
    now = utc_now()
    start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    result = await session.execute(
        select(MemoryEvent).where(
            MemoryEvent.user_id == user_id,
            MemoryEvent.created_at >= start,
            MemoryEvent.created_at < end,
        )
    )
    events = list(result.scalars().all())
    if project_root:
        events = [e for e in events if e.project_root == project_root]
    return format_events(events, title="What we did yesterday:")


async def format_open_loops(
    session: AsyncSession,
    user_id: str,
    project_root: str | None = None,
) -> str:
    query = select(MemoryEvent).where(
        MemoryEvent.user_id == user_id,
        MemoryEvent.event_type.in_(("validation_failed", "unresolved", "next_step")),
    )
    if project_root:
        query = query.where(MemoryEvent.project_root == project_root)
    result = await session.execute(query.order_by(MemoryEvent.created_at.desc()).limit(20))
    events = list(result.scalars().all())
    return format_events(events, title="Open loops:")


async def format_last_failure(
    session: AsyncSession,
    user_id: str,
    project_root: str | None = None,
) -> str:
    query = select(MemoryEvent).where(
        MemoryEvent.user_id == user_id,
        MemoryEvent.event_type.in_(("validation_failed", "background_task_failed", "error")),
    )
    if project_root:
        query = query.where(MemoryEvent.project_root == project_root)
    result = await session.execute(query.order_by(MemoryEvent.created_at.desc()).limit(1))
    event = result.scalar_one_or_none()
    if event is None:
        return "No recorded failures for this scope."
    return f"Last failure ({event.created_at.date()}): {event.summary}"


async def remember_project_decision(
    session: AsyncSession,
    user_id: str,
    *,
    project_root: str,
    text: str,
) -> MemoryFact:
    from apps.api.services.memory_kernel import MemoryKernelService
    from nova_core.schemas.settings import get_settings

    svc = MemoryKernelService(session, get_settings())
    fact = await svc.remember_fact(
        user_id,
        subject=f"project:{project_root}",
        predicate="decided",
        object_summary=text,
        user_confirmed=True,
        project_root=project_root,
    )
    session.add(
        MemoryProjectSummary(
            user_id=user_id,
            project_root=project_root,
            summary_type="decision",
            summary=text,
        )
    )
    await session.flush()
    return fact
