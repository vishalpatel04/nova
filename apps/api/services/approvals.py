"""Capability approval request lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.auth.principal import Principal
from nova_core.capabilities.model import (
    ActionApprovalStatus,
    CapabilityName,
    RiskLevel,
    compute_action_fingerprint,
)
from nova_core.models.orm import ApprovalRequest
from nova_core.schemas.errors import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event

APPROVAL_TTL_MINUTES = 30


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ApprovalRequestService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings

    async def create_request(
        self,
        principal: Principal,
        *,
        capability: CapabilityName,
        action_summary: str,
        preview: str,
        payload: dict[str, Any],
        risk_level: RiskLevel,
        session_id: str | None = None,
    ) -> ApprovalRequest:
        device_id = principal.device_id
        if not device_id:
            raise ValidationError("Device id required for approval requests")

        fingerprint = compute_action_fingerprint(capability.value, payload)
        expires_at = _utc_now() + timedelta(minutes=APPROVAL_TTL_MINUTES)
        record = ApprovalRequest(
            user_id=principal.user_id,
            device_id=device_id,
            capability=capability.value,
            action_summary=action_summary[:512],
            command_or_payload_preview=preview[:4000],
            action_fingerprint=fingerprint,
            risk_level=risk_level.value,
            status=ActionApprovalStatus.PENDING.value,
            metadata_json={"session_id": session_id, "payload": payload},
            expires_at=expires_at,
        )
        self.session.add(record)
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=device_id,
            action="approval.requested",
            resource_type="approval_request",
            resource_id=record.id,
            details={
                "capability": capability.value,
                "risk_level": risk_level.value,
                "action_summary": action_summary[:200],
            },
        )
        await self.session.flush()
        return record

    async def expire_stale(self) -> None:
        now = _utc_now()
        result = await self.session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == ActionApprovalStatus.PENDING.value,
                ApprovalRequest.expires_at < now,
            )
        )
        for record in result.scalars().all():
            record.status = ActionApprovalStatus.EXPIRED.value
            await record_audit_event(
                self.session,
                actor_type="system",
                actor_id="approval_service",
                action="approval.expired",
                resource_type="approval_request",
                resource_id=record.id,
                details={"capability": record.capability},
            )

    async def list_pending(self, principal: Principal) -> list[ApprovalRequest]:
        await self.expire_stale()
        if not principal.device_id:
            return []
        result = await self.session.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.user_id == principal.user_id,
                ApprovalRequest.device_id == principal.device_id,
                ApprovalRequest.status == ActionApprovalStatus.PENDING.value,
            )
            .order_by(ApprovalRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_approved(self, principal: Principal) -> list[ApprovalRequest]:
        await self.expire_stale()
        if not principal.device_id:
            return []
        result = await self.session.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.user_id == principal.user_id,
                ApprovalRequest.device_id == principal.device_id,
                ApprovalRequest.status == ActionApprovalStatus.APPROVED.value,
            )
            .order_by(ApprovalRequest.decided_at.desc())
        )
        return list(result.scalars().all())

    async def get_owned(self, approval_id: str, principal: Principal) -> ApprovalRequest:
        record = await self.session.get(ApprovalRequest, approval_id)
        if record is None:
            raise NotFoundError("approval_request", approval_id)
        if record.user_id != principal.user_id or record.device_id != principal.device_id:
            raise UnauthorizedError("Approval request ownership mismatch")
        return record

    async def approve(self, principal: Principal, approval_id: str) -> ApprovalRequest:
        await self.expire_stale()
        record = await self.get_owned(approval_id, principal)
        if record.status == ActionApprovalStatus.EXPIRED.value:
            raise ConflictError("Approval request expired")
        if record.status != ActionApprovalStatus.PENDING.value:
            raise ConflictError(f"Approval request is {record.status}")
        if _as_utc(record.expires_at) < _utc_now():
            record.status = ActionApprovalStatus.EXPIRED.value
            await record_audit_event(
                self.session,
                actor_type="device",
                actor_id=principal.device_id or principal.user_id,
                action="approval.expired",
                resource_type="approval_request",
                resource_id=record.id,
                details={"capability": record.capability},
            )
            raise ConflictError("Approval request expired")

        record.status = ActionApprovalStatus.APPROVED.value
        record.decided_at = _utc_now()
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action="approval.approved",
            resource_type="approval_request",
            resource_id=record.id,
            details={"capability": record.capability, "risk_level": record.risk_level},
        )
        return record

    async def reject(self, principal: Principal, approval_id: str) -> ApprovalRequest:
        await self.expire_stale()
        record = await self.get_owned(approval_id, principal)
        if record.status != ActionApprovalStatus.PENDING.value:
            raise ConflictError(f"Approval request is {record.status}")
        record.status = ActionApprovalStatus.REJECTED.value
        record.decided_at = _utc_now()
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action="approval.rejected",
            resource_type="approval_request",
            resource_id=record.id,
            details={"capability": record.capability},
        )
        return record

    async def consume(
        self,
        principal: Principal,
        approval_id: str,
        *,
        expected_fingerprint: str,
    ) -> ApprovalRequest:
        stmt = (
            update(ApprovalRequest)
            .where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.user_id == principal.user_id,
                ApprovalRequest.device_id == principal.device_id,
                ApprovalRequest.status == ActionApprovalStatus.APPROVED.value,
                ApprovalRequest.action_fingerprint == expected_fingerprint,
            )
            .values(
                status=ActionApprovalStatus.CONSUMED.value,
                consumed_at=_utc_now(),
            )
        )
        result = await self.session.execute(stmt)
        rowcount = getattr(result, "rowcount", None) or 0
        if rowcount != 1:
            locked = await self.session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
            )
            record = locked.scalar_one_or_none()
            if record is None:
                raise NotFoundError("approval_request", approval_id)
            if record.user_id != principal.user_id or record.device_id != principal.device_id:
                raise UnauthorizedError("Approval request ownership mismatch")
            if record.action_fingerprint != expected_fingerprint:
                raise ConflictError("Approval action fingerprint mismatch")
            if _as_utc(record.expires_at) < _utc_now():
                record.status = ActionApprovalStatus.EXPIRED.value
                raise ConflictError("Approval request expired")
            raise ConflictError(f"Approval request is {record.status}, expected approved")

        record = await self.session.get(ApprovalRequest, approval_id)
        assert record is not None
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action="approval.consumed",
            resource_type="approval_request",
            resource_id=record.id,
            details={"capability": record.capability},
        )
        return record
