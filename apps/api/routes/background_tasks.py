"""Background task and notification API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.background_scheduler import BackgroundSchedulerService
from apps.api.services.background_tasks import BackgroundTaskService
from apps.api.services.notifications import NotificationService
from nova_core.auth.principal import Principal
from nova_core.models.orm import BackgroundTask, BackgroundTaskRun, NotificationItem
from nova_core.schemas.api import (
    BackgroundSchedulerStatusResponse,
    BackgroundTaskCreateRequest,
    BackgroundTaskListResponse,
    BackgroundTaskResponse,
    BackgroundTaskRunListResponse,
    BackgroundTaskRunResponse,
    NotificationItemResponse,
    NotificationListResponse,
)
from nova_core.schemas.settings import get_settings

router = APIRouter(tags=["background-tasks"])


def _task_response(task: BackgroundTask) -> BackgroundTaskResponse:
    return BackgroundTaskResponse(
        id=task.id,
        user_id=task.user_id,
        device_id=task.device_id,
        project_root=task.project_root,
        task_type=task.task_type,
        title=task.title,
        prompt=task.prompt,
        schedule_kind=task.schedule_kind,
        schedule_expression=task.schedule_expression,
        status=task.status,
        last_run_at=task.last_run_at,
        next_run_at=task.next_run_at,
        last_result_summary=task.last_result_summary,
        last_error=task.last_error,
        run_count=task.run_count or 0,
        failure_count=task.failure_count or 0,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _run_response(run: BackgroundTaskRun) -> BackgroundTaskRunResponse:
    return BackgroundTaskRunResponse(
        id=run.id,
        task_id=run.task_id,
        user_id=run.user_id,
        device_id=run.device_id,
        status=run.status,
        summary=run.summary,
        error=run.error,
        evidence_json=run.evidence_json,
        attempt=run.attempt or 1,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
    )


def _notification_response(item: NotificationItem) -> NotificationItemResponse:
    return NotificationItemResponse(
        id=item.id,
        user_id=item.user_id,
        device_id=item.device_id,
        notification_type=item.notification_type,
        title=item.title,
        summary=item.summary,
        task_id=item.task_id,
        read=item.read_at is not None,
        created_at=item.created_at,
    )


@router.get("/background-tasks", response_model=BackgroundTaskListResponse)
async def list_background_tasks(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundTaskListResponse:
    svc = BackgroundTaskService(session, get_settings())
    tasks = await svc.list_tasks(principal)
    return BackgroundTaskListResponse(tasks=[_task_response(t) for t in tasks])


@router.post("/background-tasks", response_model=BackgroundTaskResponse)
async def create_background_task(
    body: BackgroundTaskCreateRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundTaskResponse:
    svc = BackgroundTaskService(session, get_settings())
    task = await svc.create_task(
        principal,
        task_type=body.task_type,
        title=body.title,
        prompt=body.prompt,
        project_root=body.project_root,
        schedule_kind=body.schedule_kind,
        schedule_expression=body.schedule_expression,
    )
    await session.commit()
    await session.refresh(task)
    return _task_response(task)


@router.get("/background-tasks/scheduler-status", response_model=BackgroundSchedulerStatusResponse)
async def background_scheduler_status(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundSchedulerStatusResponse:
    sched = BackgroundSchedulerService(session, get_settings())
    status = await sched.scheduler_status(principal)
    return BackgroundSchedulerStatusResponse(**status)


@router.get("/background-tasks/{task_id}", response_model=BackgroundTaskResponse)
async def get_background_task(
    task_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundTaskResponse:
    svc = BackgroundTaskService(session, get_settings())
    task = await svc.get_task(principal, task_id)
    return _task_response(task)


@router.post("/background-tasks/{task_id}/pause", response_model=BackgroundTaskResponse)
async def pause_background_task(
    task_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundTaskResponse:
    svc = BackgroundTaskService(session, get_settings())
    task = await svc.pause_task(principal, task_id)
    await session.commit()
    await session.refresh(task)
    return _task_response(task)


@router.post("/background-tasks/{task_id}/resume", response_model=BackgroundTaskResponse)
async def resume_background_task(
    task_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundTaskResponse:
    svc = BackgroundTaskService(session, get_settings())
    task = await svc.resume_task(principal, task_id)
    await session.commit()
    await session.refresh(task)
    return _task_response(task)


@router.post("/background-tasks/{task_id}/cancel", response_model=BackgroundTaskResponse)
async def cancel_background_task(
    task_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundTaskResponse:
    svc = BackgroundTaskService(session, get_settings())
    task = await svc.cancel_task(principal, task_id)
    await session.commit()
    await session.refresh(task)
    return _task_response(task)


@router.get("/background-tasks/{task_id}/runs", response_model=BackgroundTaskRunListResponse)
async def list_background_task_runs(
    task_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundTaskRunListResponse:
    svc = BackgroundTaskService(session, get_settings())
    runs = await svc.list_runs(principal, task_id)
    return BackgroundTaskRunListResponse(runs=[_run_response(r) for r in runs])


@router.post("/background-tasks/{task_id}/run-now", response_model=BackgroundTaskRunResponse)
async def run_background_task_now(
    task_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundTaskRunResponse:
    sched = BackgroundSchedulerService(session, get_settings())
    run = await sched.run_task_now(principal, task_id)
    await session.commit()
    await session.refresh(run)
    return _run_response(run)


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> NotificationListResponse:
    svc = NotificationService(session)
    items, unread = await svc.list_notifications(principal)
    return NotificationListResponse(
        notifications=[_notification_response(i) for i in items],
        unread_count=unread,
    )


@router.post("/notifications/{notification_id}/read", response_model=NotificationItemResponse)
async def mark_notification_read(
    notification_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> NotificationItemResponse:
    svc = NotificationService(session)
    item = await svc.mark_read(principal, notification_id)
    await session.commit()
    await session.refresh(item)
    return _notification_response(item)


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    svc = NotificationService(session)
    count = await svc.mark_all_read(principal)
    await session.commit()
    return {"marked_read": count}
