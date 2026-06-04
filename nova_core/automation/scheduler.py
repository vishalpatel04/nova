"""Phase 3C safe scheduler dispatcher skeleton — paused, approval-gated, auditable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.orm import ScheduledTask
from nova_core.sentry.audit import record_audit_event
from nova_core.utils.time import utc_now


@dataclass(frozen=True)
class SchedulerDispatchPreview:
    task_id: str
    title: str
    provider: str
    action: str
    status: str
    would_run: bool
    requires_approval: bool
    retry_count: int
    next_retry_at: str | None
    reason: str


class SchedulerDispatcher:
    """Inspects paused tasks without executing automations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def preview_tasks(self, tasks: list[ScheduledTask]) -> list[SchedulerDispatchPreview]:
        previews: list[SchedulerDispatchPreview] = []
        for task in tasks:
            retry_meta = self._retry_metadata(task)
            previews.append(
                SchedulerDispatchPreview(
                    task_id=task.id,
                    title=task.title,
                    provider=task.provider,
                    action=task.action,
                    status=task.status,
                    would_run=False,
                    requires_approval=True,
                    retry_count=int(retry_meta.get("retry_count", 0)),
                    next_retry_at=retry_meta.get("next_retry_at"),
                    reason="scheduler_paused_phase_3c",
                )
            )
        return previews

    async def dispatch_tick(
        self,
        *,
        actor_type: str,
        actor_id: str,
        tasks: list[ScheduledTask],
    ) -> dict[str, Any]:
        """Record audit replay for a scheduler tick without executing tasks."""
        previews = await self.preview_tasks(tasks)
        await record_audit_event(
            self.session,
            actor_type=actor_type,
            actor_id=actor_id,
            action="scheduler.tick",
            resource_type="scheduler",
            resource_id="dispatcher",
            details={
                "executed": False,
                "task_count": len(previews),
                "tasks": [
                    {
                        "task_id": p.task_id,
                        "status": p.status,
                        "would_run": p.would_run,
                        "requires_approval": p.requires_approval,
                        "reason": p.reason,
                    }
                    for p in previews
                ],
            },
        )
        await self.session.commit()
        return {
            "executed": False,
            "paused": True,
            "task_count": len(previews),
            "tasks": [p.__dict__ for p in previews],
            "timestamp": utc_now().isoformat(),
        }

    def _retry_metadata(self, task: ScheduledTask) -> dict[str, Any]:
        payload = task.payload if isinstance(task.payload, dict) else {}
        retry = payload.get("_retry", {})
        if isinstance(retry, dict):
            return retry
        return {}
