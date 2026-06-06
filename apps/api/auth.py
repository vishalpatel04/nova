"""FastAPI authentication dependencies."""

from collections.abc import Callable
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
            token_role="admin",
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
    ticket = websocket.query_params.get("ticket")
    if not ticket and not settings.require_device_token:
        return Principal(
            principal_type="user",
            principal_id=settings.nova_default_user_id,
            user_id=settings.nova_default_user_id,
            token_role="admin",
        )
    if not ticket:
        raise UnauthorizedError("WebSocket ticket required")
    auth = AuthService(session, settings)
    return await auth.consume_websocket_ticket(ticket)


def require_roles(*roles: str) -> Callable[..., object]:
    async def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if principal.token_role not in roles:
            raise UnauthorizedError("Credential scope does not permit this operation")
        return principal

    return dependency
