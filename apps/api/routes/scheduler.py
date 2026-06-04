"""Phase 3C scheduler routes — paused dispatcher skeleton."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.runtime import AutomationService
from nova_core.auth.principal import Principal
from nova_core.automation.scheduler import SchedulerDispatcher
from nova_core.schemas.api import SchedulerStatusResponse, SchedulerTickResponse
from nova_core.schemas.settings import get_settings

router = APIRouter(tags=["scheduler"])


@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def scheduler_status(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> SchedulerStatusResponse:
    svc = AutomationService(session, get_settings())
    tasks = await svc.list_scheduled(principal)
    dispatcher = SchedulerDispatcher(session)
    previews = await dispatcher.preview_tasks(tasks)
    return SchedulerStatusResponse(
        paused=True,
        task_count=len(previews),
        tasks=[p.__dict__ for p in previews],
    )


@router.post("/scheduler/tick", response_model=SchedulerTickResponse)
async def scheduler_tick(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> SchedulerTickResponse:
    svc = AutomationService(session, get_settings())
    tasks = await svc.list_scheduled(principal)
    dispatcher = SchedulerDispatcher(session)
    result = await dispatcher.dispatch_tick(
        actor_type=principal.principal_type,
        actor_id=principal.principal_id,
        tasks=tasks,
    )
    return SchedulerTickResponse(**result)
