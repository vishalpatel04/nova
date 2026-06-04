"""Phase 3B runtime routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.runtime import AutomationService, ChatSessionService
from nova_core.auth.principal import Principal
from nova_core.models.orm import AutomationRun, ChatMessageRecord, ChatSession, ScheduledTask
from nova_core.providers.runtime import ProviderRuntime
from nova_core.schemas.api import (
    AutomationExecuteRequest,
    AutomationRunResponse,
    ChatMessageRecordResponse,
    ChatSessionResponse,
    CompanionPromptRequest,
    CompanionPromptResponse,
    ProviderHealthResponse,
    RuntimeStatusResponse,
    ScheduledTaskCreateRequest,
    ScheduledTaskResponse,
)
from nova_core.schemas.settings import get_settings

router = APIRouter(tags=["runtime"])


@router.get("/runtime/status", response_model=RuntimeStatusResponse)
async def runtime_status(
    _principal: Annotated[Principal, Depends(require_roles("admin", "client"))],
) -> RuntimeStatusResponse:
    settings = get_settings()
    runtime = ProviderRuntime(settings)
    checks = await runtime.health_checks()
    return RuntimeStatusResponse(
        local_first=True,
        paid_providers_enabled=settings.nova_paid_providers_enabled,
        providers=[
            ProviderHealthResponse(
                provider=check.provider.value,
                configured=check.configured,
                paid=check.paid,
                healthy=check.healthy,
                mode=check.mode,
                detail=check.detail,
            )
            for check in checks
        ],
    )


@router.get("/chat/sessions", response_model=list[ChatSessionResponse])
async def list_chat_sessions(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> list[ChatSessionResponse]:
    svc = ChatSessionService(session)
    sessions = await svc.list_sessions(principal)
    return [_session_response(s, []) for s in sessions]


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionResponse:
    svc = ChatSessionService(session)
    chat_session = await svc.get_session(principal, session_id)
    if chat_session is None:
        from nova_core.schemas.errors import NotFoundError

        raise NotFoundError("ChatSession", session_id)
    messages = await session.execute(
        select(ChatMessageRecord)
        .where(ChatMessageRecord.session_id == chat_session.id)
        .order_by(ChatMessageRecord.created_at)
    )
    return _session_response(chat_session, list(messages.scalars().all()))


@router.post("/automation/execute", response_model=AutomationRunResponse)
async def execute_automation(
    body: AutomationExecuteRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> AutomationRunResponse:
    svc = AutomationService(session, get_settings())
    run = await svc.execute(
        principal,
        provider=body.provider,
        action=body.action,
        payload=body.payload,
        approval_id=body.approval_id,
        dry_run=body.dry_run,
    )
    return _automation_response(run)


@router.post("/automation/schedules", response_model=ScheduledTaskResponse, status_code=201)
async def create_schedule(
    body: ScheduledTaskCreateRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ScheduledTaskResponse:
    svc = AutomationService(session, get_settings())
    task = await svc.schedule(
        principal,
        title=body.title,
        provider=body.provider,
        action=body.action,
        schedule=body.schedule,
        payload=body.payload,
    )
    return _scheduled_response(task)


@router.get("/automation/schedules", response_model=list[ScheduledTaskResponse])
async def list_schedules(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> list[ScheduledTaskResponse]:
    svc = AutomationService(session, get_settings())
    return [_scheduled_response(task) for task in await svc.list_scheduled(principal)]


@router.post("/companion/prompts", response_model=CompanionPromptResponse, status_code=202)
async def companion_prompt(
    body: CompanionPromptRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> CompanionPromptResponse:
    svc = ChatSessionService(session)
    chat_session = await svc.get_or_create(principal, None, title="Companion Prompt")
    message = await svc.append_message(
        chat_session,
        role="user",
        content=body.message,
        intent="remote_prompt",
        routing={"target_device_id": body.target_device_id},
    )
    await session.commit()
    return CompanionPromptResponse(
        status="queued",
        session_id=chat_session.id,
        message_id=message.id,
    )


def _session_response(
    session: ChatSession, messages: list[ChatMessageRecord]
) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        provider_mode=session.provider_mode,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[
            ChatMessageRecordResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                intent=m.intent,
                blocked=m.blocked,
                routing=m.routing,
                token_usage=m.token_usage,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


def _automation_response(run: AutomationRun) -> AutomationRunResponse:
    return AutomationRunResponse(
        id=run.id,
        provider=run.provider,
        action=run.action,
        status=run.status,
        requires_approval=run.requires_approval,
        approval_id=run.approval_id,
        result_payload=run.result_payload,
        error_message=run.error_message,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _scheduled_response(task: ScheduledTask) -> ScheduledTaskResponse:
    return ScheduledTaskResponse(
        id=task.id,
        title=task.title,
        provider=task.provider,
        action=task.action,
        schedule=task.schedule,
        status=task.status,
        created_at=task.created_at,
    )
