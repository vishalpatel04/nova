"""Capability approval API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.approvals import ApprovalRequestService
from nova_core.auth.principal import Principal
from nova_core.capabilities.model import CapabilityName, RiskLevel
from nova_core.models.orm import ApprovalRequest
from nova_core.schemas.api import (
    ApprovalActionableListResponse,
    ApprovalPendingListResponse,
    ApprovalRequestCreateBody,
    ApprovalRequestResponse,
)
from nova_core.schemas.settings import get_settings

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _approval_response(record: ApprovalRequest) -> ApprovalRequestResponse:
    return ApprovalRequestResponse(
        id=record.id,
        capability=record.capability,
        action_summary=record.action_summary,
        command_or_payload_preview=record.command_or_payload_preview,
        risk_level=record.risk_level,
        status=record.status,
        created_at=record.created_at,
        expires_at=record.expires_at,
        decided_at=record.decided_at,
        consumed_at=record.consumed_at,
    )


@router.post("/request", response_model=ApprovalRequestResponse)
async def create_approval_request(
    body: ApprovalRequestCreateBody,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalRequestResponse:
    settings = get_settings()
    svc = ApprovalRequestService(session, settings)
    try:
        capability = CapabilityName(body.capability)
    except ValueError as exc:
        from nova_core.schemas.errors import ValidationError

        raise ValidationError(f"Unknown capability: {body.capability}") from exc
    record = await svc.create_request(
        principal,
        capability=capability,
        action_summary=body.action_summary,
        preview=body.command_or_payload_preview,
        payload=body.payload,
        risk_level=RiskLevel(body.risk_level),
        session_id=body.session_id,
    )
    await session.commit()
    return _approval_response(record)


@router.get("/pending", response_model=ApprovalPendingListResponse)
async def list_pending_approvals(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalPendingListResponse:
    settings = get_settings()
    svc = ApprovalRequestService(session, settings)
    items = await svc.list_pending(principal)
    await session.commit()
    return ApprovalPendingListResponse(items=[_approval_response(item) for item in items])


@router.get("/actionable", response_model=ApprovalActionableListResponse)
async def list_actionable_approvals(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalActionableListResponse:
    settings = get_settings()
    svc = ApprovalRequestService(session, settings)
    pending = await svc.list_pending(principal)
    approved = await svc.list_approved(principal)
    await session.commit()
    return ApprovalActionableListResponse(
        pending=[_approval_response(item) for item in pending],
        approved=[_approval_response(item) for item in approved],
    )


@router.post("/{approval_id}/approve", response_model=ApprovalRequestResponse)
async def approve_request(
    approval_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalRequestResponse:
    settings = get_settings()
    svc = ApprovalRequestService(session, settings)
    record = await svc.approve(principal, approval_id)
    await session.commit()
    return _approval_response(record)


@router.post("/{approval_id}/reject", response_model=ApprovalRequestResponse)
async def reject_request(
    approval_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalRequestResponse:
    settings = get_settings()
    svc = ApprovalRequestService(session, settings)
    record = await svc.reject(principal, approval_id)
    await session.commit()
    return _approval_response(record)
