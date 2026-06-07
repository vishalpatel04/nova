"""Session-scoped pending tool intent memory for multi-turn workflows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.auth.principal import Principal
from nova_core.models.enums import PendingToolIntentStatus, PendingToolIntentType
from nova_core.models.orm import PendingToolIntent
from nova_core.schemas.errors import ValidationError
from nova_core.sentry.audit import record_audit_event

PENDING_INTENT_TTL_MINUTES = 5

SUGGESTED_SCOPES = ["Desktop", "Documents", "Downloads", "Projects"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class PendingToolIntentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def cancel_active_for_session(
        self,
        principal: Principal,
        session_id: str,
    ) -> None:
        if not principal.device_id:
            return
        await self.session.execute(
            update(PendingToolIntent)
            .where(
                PendingToolIntent.session_id == session_id,
                PendingToolIntent.user_id == principal.user_id,
                PendingToolIntent.device_id == principal.device_id,
                PendingToolIntent.status == PendingToolIntentStatus.PENDING.value,
            )
            .values(
                status=PendingToolIntentStatus.CANCELLED.value,
                consumed_at=_utc_now(),
            )
        )
        await self.session.flush()

    async def create_scope_confirmation(
        self,
        principal: Principal,
        *,
        session_id: str,
        query: str,
    ) -> PendingToolIntent:
        if not principal.device_id:
            raise ValidationError("Device id required for pending tool intent")
        if not query.strip():
            raise ValidationError("Search query required")

        await self.cancel_active_for_session(principal, session_id)

        expires_at = _utc_now() + timedelta(minutes=PENDING_INTENT_TTL_MINUTES)
        record = PendingToolIntent(
            session_id=session_id,
            user_id=principal.user_id,
            device_id=principal.device_id,
            intent_type=PendingToolIntentType.PERSONAL_SEARCH_SCOPE_CONFIRMATION.value,
            payload_json={
                "query": query.strip()[:256],
                "suggested_scopes": list(SUGGESTED_SCOPES),
                "requested_scope_mode": "choose_scope",
            },
            status=PendingToolIntentStatus.PENDING.value,
            expires_at=expires_at,
        )
        self.session.add(record)
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id,
            action="pending_tool_intent.created",
            resource_type="pending_tool_intent",
            resource_id=record.id,
            details={"intent_type": record.intent_type, "session_id": session_id},
        )
        await self.session.flush()
        return record

    async def _fetch_pending(
        self,
        principal: Principal,
        session_id: str,
    ) -> PendingToolIntent | None:
        if not principal.device_id:
            return None
        result = await self.session.execute(
            select(PendingToolIntent).where(
                PendingToolIntent.session_id == session_id,
                PendingToolIntent.user_id == principal.user_id,
                PendingToolIntent.device_id == principal.device_id,
                PendingToolIntent.status == PendingToolIntentStatus.PENDING.value,
            )
        )
        return result.scalar_one_or_none()

    async def get_active(
        self,
        principal: Principal,
        session_id: str,
    ) -> PendingToolIntent | None:
        record = await self._fetch_pending(principal, session_id)
        if record is None:
            return None
        if _as_utc(record.expires_at) <= _utc_now():
            await self._mark_expired(record)
            return None
        return record

    async def get_recently_expired(
        self,
        principal: Principal,
        session_id: str,
    ) -> PendingToolIntent | None:
        if not principal.device_id:
            return None
        result = await self.session.execute(
            select(PendingToolIntent)
            .where(
                PendingToolIntent.session_id == session_id,
                PendingToolIntent.user_id == principal.user_id,
                PendingToolIntent.device_id == principal.device_id,
                PendingToolIntent.status == PendingToolIntentStatus.EXPIRED.value,
            )
            .order_by(PendingToolIntent.consumed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _mark_expired(self, record: PendingToolIntent) -> None:
        record.status = PendingToolIntentStatus.EXPIRED.value
        record.consumed_at = _utc_now()
        await self.session.flush()

    async def consume(
        self,
        record: PendingToolIntent,
        *,
        status: PendingToolIntentStatus = PendingToolIntentStatus.CONSUMED,
    ) -> None:
        record.status = status.value
        record.consumed_at = _utc_now()
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=record.device_id,
            action="pending_tool_intent.consumed",
            resource_type="pending_tool_intent",
            resource_id=record.id,
            details={"status": status.value},
        )
        await self.session.flush()

    def payload_query(self, record: PendingToolIntent) -> str:
        payload = record.payload_json or {}
        return str(payload.get("query", "")).strip()
