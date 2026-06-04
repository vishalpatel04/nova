"""Device pairing and token management routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import get_bootstrap_or_principal
from apps.api.deps import get_db_session
from apps.api.services.pairing import AuthService, PairingService
from nova_core.auth.principal import Principal
from nova_core.schemas.settings import get_settings

router = APIRouter(prefix="/pairing", tags=["pairing"])


class PairingCodeCreateRequest(BaseModel):
    device_type: str
    proposed_device_id: str | None = None
    proposed_name: str | None = None


class PairingCodeCreateResponse(BaseModel):
    pairing_id: str
    code: str
    expires_at: str
    requires_approval: bool


class PairingClaimRequest(BaseModel):
    code: str
    device_id: str
    name: str
    device_type: str
    hostname: str | None = None
    os_version: str | None = None
    architecture: str | None = None


class PairingClaimResponse(BaseModel):
    pairing_id: str
    status: str
    device_id: str
    token: str | None = None
    message: str


class PairingApproveResponse(BaseModel):
    device_id: str
    token: str
    status: str = "claimed"


class TokenRotateResponse(BaseModel):
    device_id: str
    token: str


class DeviceRevokeRequest(BaseModel):
    reason: str | None = None


class WebSocketTicketRequest(BaseModel):
    scope: str
    mission_id: str | None = None


class WebSocketTicketResponse(BaseModel):
    ticket: str
    expires_in_seconds: int


@router.post("/codes", response_model=PairingCodeCreateResponse, status_code=201)
async def create_pairing_code(
    body: PairingCodeCreateRequest,
    principal: Annotated[Principal, Depends(get_bootstrap_or_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> PairingCodeCreateResponse:
    if principal.token_role != "admin":
        from nova_core.schemas.errors import UnauthorizedError

        raise UnauthorizedError("Admin credential required")
    settings = get_settings()
    svc = PairingService(session, settings)
    pairing, code = await svc.create_pairing_code(
        user_id=principal.user_id,
        device_type=body.device_type,
        proposed_device_id=body.proposed_device_id,
        proposed_name=body.proposed_name,
    )
    return PairingCodeCreateResponse(
        pairing_id=pairing.id,
        code=code,
        expires_at=pairing.expires_at.isoformat(),
        requires_approval=pairing.requires_approval,
    )


@router.post("/claim", response_model=PairingClaimResponse)
async def claim_pairing_code(
    body: PairingClaimRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> PairingClaimResponse:
    settings = get_settings()
    svc = PairingService(session, settings)
    pairing, token = await svc.claim_pairing_code(
        code=body.code,
        device_id=body.device_id,
        name=body.name,
        device_type=body.device_type,
        hostname=body.hostname,
        os_version=body.os_version,
        architecture=body.architecture,
        client_ip=request.client.host if request.client else None,
    )
    if token:
        return PairingClaimResponse(
            pairing_id=pairing.id,
            status="claimed",
            device_id=body.device_id,
            token=token,
            message="Device paired successfully",
        )
    return PairingClaimResponse(
        pairing_id=pairing.id,
        status="pending_approval",
        device_id=body.device_id,
        message="Pairing claim submitted — awaiting approval",
    )


@router.post("/{pairing_id}/approve", response_model=PairingApproveResponse)
async def approve_pairing(
    pairing_id: str,
    principal: Annotated[Principal, Depends(get_bootstrap_or_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> PairingApproveResponse:
    if principal.token_role != "admin":
        from nova_core.schemas.errors import UnauthorizedError

        raise UnauthorizedError("Admin credential required")
    settings = get_settings()
    svc = PairingService(session, settings)
    device_id, token = await svc.approve_pairing(pairing_id, principal)
    return PairingApproveResponse(device_id=device_id, token=token)


@router.post("/ws-tickets", response_model=WebSocketTicketResponse, tags=["realtime"])
async def issue_websocket_ticket(
    body: WebSocketTicketRequest,
    principal: Annotated[Principal, Depends(get_bootstrap_or_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> WebSocketTicketResponse:
    settings = get_settings()
    svc = AuthService(session, settings)
    ttl = 60
    ticket, _row = await svc.issue_websocket_ticket(
        principal,
        scope=body.scope,
        mission_id=body.mission_id,
        ttl_seconds=ttl,
    )
    return WebSocketTicketResponse(ticket=ticket, expires_in_seconds=ttl)


devices_router = APIRouter(prefix="/devices", tags=["devices"])


@devices_router.post("/{device_id}/rotate-token", response_model=TokenRotateResponse)
async def rotate_device_token(
    device_id: str,
    principal: Annotated[Principal, Depends(get_bootstrap_or_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> TokenRotateResponse:
    if principal.token_role != "admin":
        from nova_core.schemas.errors import UnauthorizedError

        raise UnauthorizedError("Admin credential required")
    settings = get_settings()
    svc = PairingService(session, settings)
    token = await svc.rotate_token(device_id, principal)
    return TokenRotateResponse(device_id=device_id, token=token)


@devices_router.post("/{device_id}/revoke")
async def revoke_device(
    device_id: str,
    body: DeviceRevokeRequest,
    principal: Annotated[Principal, Depends(get_bootstrap_or_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    if principal.token_role != "admin":
        from nova_core.schemas.errors import UnauthorizedError

        raise UnauthorizedError("Admin credential required")
    settings = get_settings()
    svc = PairingService(session, settings)
    await svc.revoke_device(device_id, principal, body.reason)
    return {"status": "revoked", "device_id": device_id}
