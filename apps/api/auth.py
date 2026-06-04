"""FastAPI authentication dependencies."""

from typing import Annotated

from fastapi import Depends, Header, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_app_state, get_db_session
from apps.api.services.pairing import AuthService
from nova_core.auth.principal import Principal
from nova_core.schemas.errors import UnauthorizedError


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


async def get_optional_principal(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_db_session),
) -> Principal | None:
    settings = get_app_state().settings
    token = _extract_bearer(authorization)
    if token:
        auth = AuthService(session, settings)
        return await auth.authenticate_token(token)
    if not settings.require_device_token:
        return Principal(
            principal_type="user",
            principal_id=settings.nova_default_user_id,
            user_id=settings.nova_default_user_id,
        )
    return None


async def get_current_principal(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> Principal:
    if principal is None:
        raise UnauthorizedError("Authentication required")
    return principal


async def get_bootstrap_or_principal(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_db_session),
) -> Principal:
    settings = get_app_state().settings
    token = _extract_bearer(authorization)
    if not token:
        raise UnauthorizedError("Authentication required")
    auth = AuthService(session, settings)
    return await auth.authenticate_token(token)


async def authenticate_websocket(websocket: WebSocket, session: AsyncSession) -> Principal:
    settings = get_app_state().settings
    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        token = _extract_bearer(auth_header)
    if not token and not settings.require_device_token:
        return Principal(
            principal_type="user",
            principal_id=settings.nova_default_user_id,
            user_id=settings.nova_default_user_id,
        )
    if not token:
        raise UnauthorizedError("WebSocket authentication required")
    auth = AuthService(session, settings)
    return await auth.authenticate_token(token)
