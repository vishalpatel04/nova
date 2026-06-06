"""Chat API routes."""

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.chat import ChatService
from apps.api.services.stream_registry import cancel as cancel_stream
from apps.api.services.stream_registry import register, unregister
from nova_core.auth.principal import Principal
from nova_core.providers.stream_context import StreamCancelToken
from nova_core.schemas.api import ChatRequest, ChatResponse, ChatStreamCancelResponse
from nova_core.schemas.settings import get_settings

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    settings = get_settings()
    svc = ChatService(session, settings)
    result = await svc.handle_message(
        message=body.message,
        principal=principal,
        session_id=body.session_id,
        stream=body.stream,
    )
    return ChatResponse(
        response=result["response"],
        intent=result.get("intent", "general"),
        blocked=bool(result.get("blocked", False)),
        session_id=result.get("session_id"),
        routing=result.get("routing"),
        token_usage=result.get("token_usage"),
        approval_required=bool(result.get("approval_required", False)),
        approval_id=result.get("approval_id"),
        risk_level=result.get("risk_level"),
    )


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    settings = get_settings()
    svc = ChatService(session, settings)
    cancel_token = StreamCancelToken()

    async def event_generator() -> AsyncIterator[str]:
        register(cancel_token, owner_id=principal.principal_id)
        try:
            async for event in svc.stream_message(
                message=body.message,
                principal=principal,
                session_id=body.session_id,
                cancel=cancel_token,
            ):
                payload = json.dumps(event.get("data", {}))
                yield f"event: {event['event']}\ndata: {payload}\n\n"
        except Exception:
            payload = json.dumps({"message": "Streaming response failed"})
            yield f"event: error\ndata: {payload}\n\n"
        finally:
            unregister(cancel_token.stream_id, owner_id=principal.principal_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-NOVA-Stream-Id": cancel_token.stream_id,
        },
    )


@router.post("/chat/stream/{stream_id}/cancel", response_model=ChatStreamCancelResponse)
async def chat_stream_cancel(
    stream_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
) -> ChatStreamCancelResponse:
    cancelled = cancel_stream(stream_id, owner_id=principal.principal_id)
    return ChatStreamCancelResponse(stream_id=stream_id, cancelled=cancelled)
