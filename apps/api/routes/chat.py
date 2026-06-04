"""Chat API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.chat import ChatService
from nova_core.auth.principal import Principal
from nova_core.schemas.api import ChatRequest, ChatResponse
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
    )
