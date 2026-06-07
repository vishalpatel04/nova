"""Phase 3B runtime routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.companion import CompanionInboxService
from apps.api.services.runtime import AutomationService, ChatSessionService
from nova_core.auth.principal import Principal
from nova_core.models.enums import TokenState
from nova_core.models.orm import (
    AutomationRun,
    ChatMessageRecord,
    ChatSession,
    CompanionInboxItem,
    Device,
    ScheduledTask,
)
from nova_core.providers.router import ProviderName
from nova_core.providers.runtime import ProviderRuntime
from nova_core.schemas.api import (
    AutomationExecuteRequest,
    AutomationRunResponse,
    ChatMessageRecordResponse,
    ChatSessionResponse,
    CompanionInboxItemResponse,
    CompanionPromptRequest,
    CompanionPromptResponse,
    ProviderHealthResponse,
    RuntimeStatusResponse,
    ScheduledTaskCreateRequest,
    ScheduledTaskResponse,
)
from nova_core.schemas.settings import get_settings
from nova_core.tools.provider_security import scrub_runtime_detail

router = APIRouter(tags=["runtime"])


@router.get("/runtime/status", response_model=RuntimeStatusResponse)
async def runtime_status(
    _principal: Annotated[Principal, Depends(require_roles("admin", "client"))],
) -> RuntimeStatusResponse:
    settings = get_settings()
    runtime = ProviderRuntime(settings)
    checks = await runtime.health_checks()
    local_check = next((c for c in checks if c.provider == ProviderName.LOCAL), None)
    ollama_reachable = bool(local_check and local_check.healthy)
    local_model: str | None = None
    ollama_model_ready = False
    status_message: str | None = None
    provider_badge: str | None = None
    runtime_mode: str | None = None
    selected_provider: str | None = None
    selected_model: str | None = None
    fallback_reason: str | None = None
    local_available = False
    wake_word_supported = None
    voice_on_device_supported = None

    if not ollama_reachable:
        status_message = "Local model unavailable. Start Ollama."
        runtime_mode = "degraded"
        selected_provider = "local"
        selected_model = "rule_based"
        fallback_reason = "provider_unreachable"
    else:
        try:
            available = await runtime._fetch_ollama_models(ProviderName.LOCAL)
            local_model = await runtime._resolve_ollama_model(ProviderName.LOCAL)
            ollama_model_ready = local_model in available or any(
                name.startswith(local_model.split(":")[0]) for name in available
            )
            if ollama_model_ready:
                provider_badge = f"local · {local_model}"
                status_message = f"Local model active: {local_model}"
                runtime_mode = "local_ollama"
                selected_provider = ProviderName.LOCAL.value
                selected_model = local_model
                local_available = True
            else:
                status_message = (
                    f"Model {local_model} not installed. Run: ollama pull {local_model}"
                )
                runtime_mode = "degraded"
                selected_provider = ProviderName.LOCAL.value
                selected_model = "rule_based"
                fallback_reason = "no_model"
        except Exception:
            status_message = "Local model unavailable. Start Ollama."
            runtime_mode = "degraded"
            selected_provider = "local"
            selected_model = "rule_based"
            fallback_reason = "provider_unreachable"

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
                detail=scrub_runtime_detail(check.detail),
            )
            for check in checks
        ],
        local_model=local_model,
        ollama_reachable=ollama_reachable,
        ollama_model_ready=ollama_model_ready,
        provider_badge=provider_badge,
        status_message=status_message,
        runtime_mode=runtime_mode,
        selected_provider=selected_provider,
        selected_model=selected_model,
        fallback_reason=fallback_reason,
        local_available=local_available,
        wake_word_supported=wake_word_supported,
        voice_on_device_supported=voice_on_device_supported,
    )


@router.get("/chat/sessions", response_model=list[ChatSessionResponse])
async def list_chat_sessions(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> list[ChatSessionResponse]:
    svc = ChatSessionService(session)
    sessions = await svc.list_sessions(principal)
    return [_session_response(s, []) for s in sessions]


@router.get("/chat/sessions/latest", response_model=ChatSessionResponse)
async def get_latest_chat_session(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionResponse:
    svc = ChatSessionService(session)
    chat_session = await svc.get_latest_session(principal)
    if chat_session is None:
        from nova_core.schemas.errors import NotFoundError

        raise NotFoundError("ChatSession", "latest")
    messages = await session.execute(
        select(ChatMessageRecord)
        .where(ChatMessageRecord.session_id == chat_session.id)
        .order_by(ChatMessageRecord.created_at)
    )
    return _session_response(chat_session, list(messages.scalars().all()))


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
    if not body.target_device_id:
        from nova_core.schemas.errors import ValidationError

        raise ValidationError("target_device_id is required for companion prompts")

    target_result = await session.execute(select(Device).where(Device.id == body.target_device_id))
    target = target_result.scalar_one_or_none()
    if target is None:
        from nova_core.schemas.errors import NotFoundError

        raise NotFoundError("Device", body.target_device_id)
    if target.user_id != principal.user_id:
        from nova_core.schemas.errors import UnauthorizedError

        raise UnauthorizedError("Target device is not owned by this user")
    if target.token_state == TokenState.REVOKED.value:
        from nova_core.schemas.errors import UnauthorizedError

        raise UnauthorizedError("Target device is revoked")

    inbox_svc = CompanionInboxService(session)
    svc = ChatSessionService(session)
    chat_session = await svc.get_or_create(principal, None, title="Companion Prompt")
    message = await svc.append_message(
        chat_session,
        role="user",
        content=body.message,
        intent="remote_prompt",
        routing={"target_device_id": body.target_device_id},
    )
    inbox_item = await inbox_svc.enqueue_prompt(
        principal,
        message=body.message,
        target_device_id=body.target_device_id,
        session_id=chat_session.id,
        message_id=message.id,
    )
    await session.commit()
    return CompanionPromptResponse(
        status="queued",
        session_id=chat_session.id,
        message_id=message.id,
        inbox_item_id=inbox_item.id,
    )


@router.get("/companion/inbox", response_model=list[CompanionInboxItemResponse])
async def companion_inbox(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
    device_id: str | None = None,
) -> list[CompanionInboxItemResponse]:
    inbox_svc = CompanionInboxService(session)
    items = await inbox_svc.list_inbox(principal, device_id=device_id)
    return [_inbox_item_response(item) for item in items]


@router.post(
    "/companion/inbox/{item_id}/delivered",
    response_model=CompanionInboxItemResponse,
)
async def companion_inbox_delivered(
    item_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> CompanionInboxItemResponse:
    inbox_svc = CompanionInboxService(session)
    item = await inbox_svc.mark_delivered(principal, item_id)
    await session.commit()
    return _inbox_item_response(item)


@router.post(
    "/companion/inbox/{item_id}/read",
    response_model=CompanionInboxItemResponse,
)
async def companion_inbox_read(
    item_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> CompanionInboxItemResponse:
    inbox_svc = CompanionInboxService(session)
    item = await inbox_svc.mark_read(principal, item_id)
    await session.commit()
    return _inbox_item_response(item)


def _inbox_item_response(item: CompanionInboxItem) -> CompanionInboxItemResponse:
    return CompanionInboxItemResponse(
        id=item.id,
        source_device_id=item.source_device_id,
        target_device_id=item.target_device_id,
        message=item.message,
        status=item.status,
        session_id=item.session_id,
        message_id=item.message_id,
        created_at=item.created_at,
        delivered_at=item.delivered_at,
        read_at=item.read_at,
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
