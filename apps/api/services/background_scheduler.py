"""Background task scheduler — poll, claim, execute, retry, notify."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.background_tasks import BackgroundTaskService
from apps.api.services.notifications import NotificationService, sanitize_notification_summary
from nova_core.auth.principal import Principal
from nova_core.background.executor import BackgroundTaskExecutor
from nova_core.background.schedules import compute_next_run
from nova_core.background.task_types import BASE_RETRY_SECONDS, MAX_RETRY_ATTEMPTS
from nova_core.models.enums import (
    BackgroundRunStatus,
    BackgroundScheduleKind,
    BackgroundTaskStatus,
    BackgroundTaskType,
    NotificationType,
)
from nova_core.models.orm import BackgroundTask, BackgroundTaskRun
from nova_core.schemas.errors import ConflictError
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BackgroundSchedulerService:
    POLL_INTERVAL_SECONDS = 30

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._task_svc = BackgroundTaskService(session, settings)
        self._executor = BackgroundTaskExecutor(session, settings)
        self._notifications = NotificationService(session)

    async def poll_and_dispatch(
        self,
        *,
        actor_type: str = "system",
        actor_id: str = "background_scheduler",
        limit: int = 10,
    ) -> dict[str, Any]:
        now = _utc_now()
        due = await self._find_due_tasks(now, limit=limit)
        executed = 0
        for task in due:
            claimed = await self._task_svc.try_claim_task(task.id)
            if claimed is None:
                continue
            await record_audit_event(
                self.session,
                actor_type=actor_type,
                actor_id=actor_id,
                action="background_task.claimed",
                resource_type="background_task",
                resource_id=task.id,
                details={},
            )
            await self._execute_claimed(claimed, actor_type=actor_type, actor_id=actor_id)
            executed += 1
        return {"due": len(due), "executed": executed}

    async def run_task_now(
        self,
        principal: Principal,
        task_id: str,
        *,
        actor_type: str = "device",
        actor_id: str | None = None,
    ) -> BackgroundTaskRun:
        task = await self._task_svc.get_task(principal, task_id)
        if task.status == BackgroundTaskStatus.RUNNING.value:
            raise ConflictError("Task is already running")
        if task.status == BackgroundTaskStatus.CANCELLED.value:
            raise ConflictError("Task is cancelled")
        if task.status == BackgroundTaskStatus.PAUSED.value:
            raise ConflictError("Task is paused — resume before run now")
        claimed = await self._task_svc.try_claim_task(task.id)
        if claimed is None:
            raise ConflictError("Could not claim task for execution")
        await record_audit_event(
            self.session,
            actor_type=actor_type,
            actor_id=actor_id or principal.device_id or "unknown",
            action="background_task.claimed",
            resource_type="background_task",
            resource_id=task.id,
            details={"trigger": "run_now"},
        )
        return await self._execute_claimed(
            claimed,
            actor_type=actor_type,
            actor_id=actor_id or principal.device_id or "unknown",
        )

    async def _find_due_tasks(self, now: datetime, *, limit: int) -> list[BackgroundTask]:
        result = await self.session.execute(
            select(BackgroundTask)
            .where(
                BackgroundTask.status == BackgroundTaskStatus.ACTIVE.value,
                BackgroundTask.next_run_at.is_not(None),
                BackgroundTask.next_run_at <= now,
            )
            .order_by(BackgroundTask.next_run_at.asc())
            .limit(limit)
        )
        candidates = list(result.scalars().all())
        eligible: list[BackgroundTask] = []
        for task in candidates:
            meta = task.metadata_json or {}
            retry_at_raw = meta.get("retry_at")
            if retry_at_raw:
                retry_at = datetime.fromisoformat(str(retry_at_raw).replace("Z", "+00:00"))
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                if retry_at > now:
                    continue
            eligible.append(task)
        return eligible

    async def _execute_claimed(
        self,
        task: BackgroundTask,
        *,
        actor_type: str,
        actor_id: str,
    ) -> BackgroundTaskRun:
        now = _utc_now()
        meta = dict(task.metadata_json or {})
        attempt = int(meta.get("retry_attempt", 0)) + 1
        run = BackgroundTaskRun(
            task_id=task.id,
            user_id=task.user_id,
            device_id=task.device_id,
            status=BackgroundRunStatus.RUNNING.value,
            attempt=attempt,
            started_at=now,
            audit_metadata={"trigger": "scheduler"},
        )
        self.session.add(run)
        await self.session.flush()

        await record_audit_event(
            self.session,
            actor_type=actor_type,
            actor_id=actor_id,
            action="background_task.started",
            resource_type="background_task",
            resource_id=task.id,
            details={"run_id": run.id, "attempt": attempt},
        )

        transient_error: str | None = None
        try:
            result = await self._executor.execute(
                task_type=task.task_type,
                project_root=task.project_root,
                prompt=task.prompt,
            )
        except Exception as exc:
            transient_error = str(exc)[:500]
            result = None

        finished = _utc_now()
        run.finished_at = finished
        task.last_run_at = finished
        task.run_count = (task.run_count or 0) + 1

        if transient_error is not None:
            return await self._handle_transient_failure(
                task, run, transient_error, meta, actor_type, actor_id
            )

        assert result is not None
        safe_summary = sanitize_notification_summary(result.summary)
        run.summary = safe_summary
        run.error = result.error
        run.evidence_json = self._bounded_evidence(result.evidence)
        task.last_result_summary = safe_summary
        task.last_error = result.error

        validation_types = {
            BackgroundTaskType.REPO_RUN_VALIDATION.value,
            BackgroundTaskType.REPO_HEALTH_CHECK.value,
        }
        was_failed = bool(meta.get("last_validation_failed"))

        if result.success:
            run.status = BackgroundRunStatus.SUCCEEDED.value
            task.last_error = None
            meta["retry_attempt"] = 0
            meta.pop("retry_at", None)
            if task.task_type in validation_types and was_failed:
                meta["last_validation_failed"] = False
                await self._notifications.create_notification(
                    user_id=task.user_id,
                    device_id=task.device_id,
                    notification_type=NotificationType.VALIDATION_RECOVERED.value,
                    title=f"Validation recovered: {task.title}",
                    summary=safe_summary,
                    task_id=task.id,
                )
            elif task.task_type == BackgroundTaskType.REMINDER_NOTE.value:
                await self._notifications.create_notification(
                    user_id=task.user_id,
                    device_id=task.device_id,
                    notification_type=NotificationType.REMINDER.value,
                    title=task.title,
                    summary=safe_summary,
                    task_id=task.id,
                )
            else:
                await self._notifications.create_notification(
                    user_id=task.user_id,
                    device_id=task.device_id,
                    notification_type=NotificationType.TASK_SUCCEEDED.value,
                    title=f"Task succeeded: {task.title}",
                    summary=safe_summary,
                    task_id=task.id,
                )
            await self._finalize_recurring(task, meta, succeeded=True)
            await record_audit_event(
                self.session,
                actor_type=actor_type,
                actor_id=actor_id,
                action="background_task.succeeded",
                resource_type="background_task",
                resource_id=task.id,
                details={"run_id": run.id},
            )
        else:
            run.status = BackgroundRunStatus.FAILED.value
            task.failure_count = (task.failure_count or 0) + 1
            if task.task_type in validation_types:
                meta["last_validation_failed"] = True
                await self._notifications.create_notification(
                    user_id=task.user_id,
                    device_id=task.device_id,
                    notification_type=NotificationType.VALIDATION_FAILED.value,
                    title=f"Validation failed: {task.title}",
                    summary=safe_summary,
                    task_id=task.id,
                    metadata={"patch_requires_approval": True},
                )
            else:
                await self._notifications.create_notification(
                    user_id=task.user_id,
                    device_id=task.device_id,
                    notification_type=NotificationType.TASK_FAILED.value,
                    title=f"Task failed: {task.title}",
                    summary=safe_summary,
                    task_id=task.id,
                )
            await self._finalize_recurring(task, meta, succeeded=False)
            await record_audit_event(
                self.session,
                actor_type=actor_type,
                actor_id=actor_id,
                action="background_task.failed",
                resource_type="background_task",
                resource_id=task.id,
                details={"run_id": run.id, "error": (result.error or "")[:200]},
            )

        task.metadata_json = meta
        await self.session.flush()
        return run

    async def _handle_transient_failure(
        self,
        task: BackgroundTask,
        run: BackgroundTaskRun,
        error: str,
        meta: dict[str, Any],
        actor_type: str,
        actor_id: str,
    ) -> BackgroundTaskRun:
        run.status = BackgroundRunStatus.FAILED.value
        run.error = error
        run.summary = "Transient execution error"
        task.failure_count = (task.failure_count or 0) + 1
        task.last_error = error
        retry_attempt = int(meta.get("retry_attempt", 0)) + 1
        meta["retry_attempt"] = retry_attempt

        if retry_attempt < MAX_RETRY_ATTEMPTS:
            backoff = BASE_RETRY_SECONDS * (2 ** (retry_attempt - 1))
            retry_at = _utc_now() + timedelta(seconds=backoff)
            meta["retry_at"] = retry_at.isoformat()
            task.status = BackgroundTaskStatus.ACTIVE.value
            task.next_run_at = retry_at
            await record_audit_event(
                self.session,
                actor_type=actor_type,
                actor_id=actor_id,
                action="background_task.retry_scheduled",
                resource_type="background_task",
                resource_id=task.id,
                details={"attempt": retry_attempt, "retry_at": retry_at.isoformat()},
            )
        else:
            meta.pop("retry_at", None)
            if task.schedule_kind == BackgroundScheduleKind.ONCE.value:
                task.status = BackgroundTaskStatus.FAILED.value
                task.next_run_at = None
            else:
                task.status = BackgroundTaskStatus.ACTIVE.value
                task.next_run_at = compute_next_run(
                    schedule_kind=task.schedule_kind,
                    schedule_expression=task.schedule_expression,
                    after=_utc_now(),
                )
            await record_audit_event(
                self.session,
                actor_type=actor_type,
                actor_id=actor_id,
                action="background_task.failed",
                resource_type="background_task",
                resource_id=task.id,
                details={"run_id": run.id, "transient": True},
            )

        task.metadata_json = meta
        await self.session.flush()
        return run

    async def _finalize_recurring(
        self, task: BackgroundTask, meta: dict[str, Any], *, succeeded: bool
    ) -> None:
        _ = succeeded
        if task.schedule_kind == BackgroundScheduleKind.ONCE.value:
            task.status = (
                BackgroundTaskStatus.SUCCEEDED.value
                if task.last_error is None
                else BackgroundTaskStatus.FAILED.value
            )
            task.next_run_at = None
        else:
            task.status = BackgroundTaskStatus.ACTIVE.value
            task.next_run_at = compute_next_run(
                schedule_kind=task.schedule_kind,
                schedule_expression=task.schedule_expression,
                after=_utc_now(),
            )
        task.metadata_json = meta

    @staticmethod
    def _bounded_evidence(evidence: dict[str, Any] | None) -> dict[str, Any] | None:
        if not evidence:
            return None
        bounded: dict[str, Any] = {}
        for key, value in evidence.items():
            if isinstance(value, str):
                bounded[key] = value[:1500]
            else:
                bounded[key] = value
        return bounded

    async def scheduler_status(self, principal: Principal | None = None) -> dict[str, Any]:
        active_result = await self.session.execute(
            select(BackgroundTask).where(BackgroundTask.status == BackgroundTaskStatus.ACTIVE.value)
        )
        active_tasks = list(active_result.scalars().all())
        failed_result = await self.session.execute(
            select(BackgroundTask).where(BackgroundTask.status == BackgroundTaskStatus.FAILED.value)
        )
        failed_tasks = list(failed_result.scalars().all())
        now = _utc_now()
        due = await self._find_due_tasks(now, limit=100)
        unread = 0
        if principal and principal.device_id:
            unread = await self._notifications.unread_count(principal)
        return {
            "active": True,
            "active_tasks": len(active_tasks),
            "failed_tasks": len(failed_tasks),
            "due_tasks": len(due),
            "unread_notifications": unread,
        }

    async def recover_stale_running(self) -> int:
        """Reset tasks stuck in running (e.g. after crash) back to active."""
        result = await self.session.execute(
            select(BackgroundTask).where(
                BackgroundTask.status == BackgroundTaskStatus.RUNNING.value
            )
        )
        count = 0
        for task in result.scalars().all():
            task.status = BackgroundTaskStatus.ACTIVE.value
            if task.next_run_at is None:
                task.next_run_at = _utc_now()
            count += 1
        if count:
            await self.session.flush()
        return count
