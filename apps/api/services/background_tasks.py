"""Background task CRUD and ownership enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.auth.principal import Principal
from nova_core.background.schedules import compute_next_run, validate_schedule_expression
from nova_core.background.task_types import (
    ALLOWED_BACKGROUND_TASK_TYPES,
    PROJECT_SCOPED_TASK_TYPES,
    REMINDER_TASK_TYPES,
    SYSTEM_SCOPED_TASK_TYPES,
)
from nova_core.models.enums import (
    BackgroundTaskStatus,
    BackgroundTaskType,
    TokenState,
)
from nova_core.models.orm import BackgroundTask, BackgroundTaskRun, Device
from nova_core.project.context import validate_project_root
from nova_core.schemas.errors import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BackgroundTaskService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        policies = settings.load_yaml("policies.yaml")
        safe_cfg = policies.get("safe_filesystem", {})
        self._allowed_roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None

    async def _validate_principal_device(self, principal: Principal) -> Device:
        if not principal.device_id:
            raise ValidationError("Device id required")
        result = await self.session.execute(select(Device).where(Device.id == principal.device_id))
        device = result.scalar_one_or_none()
        if device is None:
            raise NotFoundError("Device", principal.device_id)
        if device.user_id != principal.user_id:
            raise UnauthorizedError("Device ownership mismatch")
        if device.token_state == TokenState.REVOKED.value:
            raise UnauthorizedError("Device revoked")
        return device

    async def _get_owned_task(self, principal: Principal, task_id: str) -> BackgroundTask:
        await self._validate_principal_device(principal)
        result = await self.session.execute(
            select(BackgroundTask).where(BackgroundTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            raise NotFoundError("background_task", task_id)
        if task.user_id != principal.user_id or task.device_id != principal.device_id:
            raise UnauthorizedError("Background task ownership mismatch")
        return task

    def _validate_task_type(self, task_type: str) -> None:
        if task_type not in ALLOWED_BACKGROUND_TASK_TYPES:
            raise ValidationError(f"Unsupported task_type: {task_type}")
        blocked = ("shell", "exec", "command", "patch", "push", "webhook", "browser")
        lowered = task_type.lower()
        if any(token in lowered for token in blocked):
            raise ValidationError("Task type blocked")

    def _validate_project_for_type(self, task_type: str, project_root: str | None) -> str | None:
        if task_type in PROJECT_SCOPED_TASK_TYPES:
            if not project_root:
                raise ValidationError("project_root required for this task type")
            validation = validate_project_root(project_root, allowed_roots=self._allowed_roots)
            if not validation.allowed or validation.resolved is None:
                raise ValidationError(validation.reason or "Blocked project root")
            return str(validation.resolved)
        if task_type in SYSTEM_SCOPED_TASK_TYPES or task_type in REMINDER_TASK_TYPES:
            if project_root:
                validation = validate_project_root(project_root, allowed_roots=self._allowed_roots)
                if not validation.allowed:
                    raise ValidationError(validation.reason or "Blocked project root")
            return None
        raise ValidationError(f"Unsupported task_type: {task_type}")

    async def create_task(
        self,
        principal: Principal,
        *,
        task_type: str,
        title: str,
        prompt: str | None,
        project_root: str | None,
        schedule_kind: str,
        schedule_expression: str,
    ) -> BackgroundTask:
        await self._validate_principal_device(principal)
        self._validate_task_type(task_type)
        try:
            validate_schedule_expression(schedule_kind, schedule_expression)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        resolved_root = self._validate_project_for_type(task_type, project_root)
        now = _utc_now()
        next_run = compute_next_run(
            schedule_kind=schedule_kind,
            schedule_expression=schedule_expression,
            after=now,
        )
        task = BackgroundTask(
            user_id=principal.user_id,
            device_id=principal.device_id or "",
            project_root=resolved_root,
            task_type=task_type,
            title=title.strip()[:255],
            prompt=(prompt or "").strip()[:2000] or None,
            schedule_kind=schedule_kind,
            schedule_expression=schedule_expression.strip(),
            status=BackgroundTaskStatus.ACTIVE.value,
            next_run_at=next_run,
            metadata_json={"retry_attempt": 0},
        )
        self.session.add(task)
        await self.session.flush()
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or "unknown",
            action="background_task.created",
            resource_type="background_task",
            resource_id=task.id,
            details={
                "task_type": task_type,
                "schedule_kind": schedule_kind,
                "schedule_expression": schedule_expression,
            },
        )
        return task

    async def list_tasks(self, principal: Principal) -> list[BackgroundTask]:
        await self._validate_principal_device(principal)
        result = await self.session.execute(
            select(BackgroundTask)
            .where(
                BackgroundTask.user_id == principal.user_id,
                BackgroundTask.device_id == principal.device_id,
            )
            .order_by(BackgroundTask.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_task(self, principal: Principal, task_id: str) -> BackgroundTask:
        return await self._get_owned_task(principal, task_id)

    async def pause_task(self, principal: Principal, task_id: str) -> BackgroundTask:
        task = await self._get_owned_task(principal, task_id)
        if task.status == BackgroundTaskStatus.CANCELLED.value:
            raise ConflictError("Task is cancelled")
        if task.status == BackgroundTaskStatus.PAUSED.value:
            return task
        if task.status == BackgroundTaskStatus.RUNNING.value:
            raise ConflictError("Cannot pause while running")
        task.status = BackgroundTaskStatus.PAUSED.value
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or "unknown",
            action="background_task.paused",
            resource_type="background_task",
            resource_id=task.id,
            details={},
        )
        await self.session.flush()
        return task

    async def resume_task(self, principal: Principal, task_id: str) -> BackgroundTask:
        task = await self._get_owned_task(principal, task_id)
        if task.status == BackgroundTaskStatus.CANCELLED.value:
            raise ConflictError("Task is cancelled")
        if task.status not in {
            BackgroundTaskStatus.PAUSED.value,
            BackgroundTaskStatus.FAILED.value,
        }:
            if task.status == BackgroundTaskStatus.ACTIVE.value:
                return task
            raise ConflictError(f"Cannot resume task in status {task.status}")
        task.status = BackgroundTaskStatus.ACTIVE.value
        task.next_run_at = compute_next_run(
            schedule_kind=task.schedule_kind,
            schedule_expression=task.schedule_expression,
            after=_utc_now(),
        )
        meta = dict(task.metadata_json or {})
        meta["retry_attempt"] = 0
        meta.pop("retry_at", None)
        task.metadata_json = meta
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or "unknown",
            action="background_task.resumed",
            resource_type="background_task",
            resource_id=task.id,
            details={"next_run_at": task.next_run_at.isoformat() if task.next_run_at else None},
        )
        await self.session.flush()
        return task

    async def cancel_task(self, principal: Principal, task_id: str) -> BackgroundTask:
        task = await self._get_owned_task(principal, task_id)
        if task.status == BackgroundTaskStatus.CANCELLED.value:
            return task
        if task.status == BackgroundTaskStatus.RUNNING.value:
            raise ConflictError("Cannot cancel while running")
        task.status = BackgroundTaskStatus.CANCELLED.value
        task.next_run_at = None
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or "unknown",
            action="background_task.cancelled",
            resource_type="background_task",
            resource_id=task.id,
            details={},
        )
        await self.session.flush()
        return task

    async def list_runs(self, principal: Principal, task_id: str) -> list[BackgroundTaskRun]:
        await self._get_owned_task(principal, task_id)
        from nova_core.models.orm import BackgroundTaskRun

        result = await self.session.execute(
            select(BackgroundTaskRun)
            .where(BackgroundTaskRun.task_id == task_id)
            .order_by(BackgroundTaskRun.created_at.desc())
            .limit(50)
        )
        return list(result.scalars().all())

    async def try_claim_task(self, task_id: str) -> BackgroundTask | None:
        """Atomically claim an active task for execution."""
        now = _utc_now()
        stmt = (
            update(BackgroundTask)
            .where(
                BackgroundTask.id == task_id,
                BackgroundTask.status == BackgroundTaskStatus.ACTIVE.value,
            )
            .values(status=BackgroundTaskStatus.RUNNING.value, updated_at=now)
        )
        result = await self.session.execute(stmt)
        if getattr(result, "rowcount", 0) == 0:
            return None
        locked = await self.session.execute(
            select(BackgroundTask).where(BackgroundTask.id == task_id).with_for_update()
        )
        return locked.scalar_one_or_none()

    @staticmethod
    def task_to_dict(task: BackgroundTask) -> dict[str, Any]:
        return {
            "id": task.id,
            "user_id": task.user_id,
            "device_id": task.device_id,
            "project_root": task.project_root,
            "task_type": task.task_type,
            "title": task.title,
            "prompt": task.prompt,
            "schedule_kind": task.schedule_kind,
            "schedule_expression": task.schedule_expression,
            "status": task.status,
            "last_run_at": task.last_run_at,
            "next_run_at": task.next_run_at,
            "last_result_summary": task.last_result_summary,
            "last_error": task.last_error,
            "run_count": task.run_count,
            "failure_count": task.failure_count,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    @staticmethod
    def default_title_for_type(task_type: str) -> str:
        mapping = {
            BackgroundTaskType.REPO_HEALTH_CHECK.value: "Daily repo health check",
            BackgroundTaskType.REPO_RUN_VALIDATION.value: "Scheduled repo validation",
            BackgroundTaskType.REPO_INSPECT.value: "Scheduled repo inspect",
            BackgroundTaskType.PROJECT_SUMMARY.value: "Project summary",
            BackgroundTaskType.SYSTEM_STATUS.value: "System status check",
            BackgroundTaskType.REMINDER_NOTE.value: "Reminder",
        }
        return mapping.get(task_type, "Background task")

    @staticmethod
    def infer_task_type_from_text(text: str) -> str | None:
        lowered = text.lower()
        if "validation" in lowered or "validate" in lowered:
            return BackgroundTaskType.REPO_RUN_VALIDATION.value
        if "inspect" in lowered or "health" in lowered:
            return BackgroundTaskType.REPO_HEALTH_CHECK.value
        if "reminder" in lowered:
            return BackgroundTaskType.REMINDER_NOTE.value
        if "system status" in lowered:
            return BackgroundTaskType.SYSTEM_STATUS.value
        return None
