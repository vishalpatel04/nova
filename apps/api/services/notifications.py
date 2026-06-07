"""Device-scoped notification inbox."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.auth.principal import Principal
from nova_core.background.executor import BackgroundTaskExecutor
from nova_core.models.enums import TokenState
from nova_core.models.orm import Device, NotificationItem
from nova_core.schemas.errors import NotFoundError, UnauthorizedError, ValidationError
from nova_core.sentry.audit import record_audit_event

_BLOCKED_PATTERNS = (
    r"nova_bts_",
    r"nova_cli_",
    r"nova_wrk_",
    r"api[_-]?key",
    r"password",
    r"secret",
    r"token",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def sanitize_notification_summary(text: str) -> str:
    """Strip secrets and protected content from notification summaries."""
    cleaned = BackgroundTaskExecutor.sanitize_summary(text)
    for pattern in _BLOCKED_PATTERNS:
        cleaned = re.sub(pattern, "[redacted]", cleaned, flags=re.IGNORECASE)
    return cleaned[:1000]


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _validate_device(self, principal: Principal) -> None:
        if not principal.device_id:
            raise ValidationError("Device id required")
        result = await self.session.execute(select(Device).where(Device.id == principal.device_id))
        device = result.scalar_one_or_none()
        if device is None:
            raise NotFoundError("Device", principal.device_id)
        if device.user_id != principal.user_id:
            raise UnauthorizedError("Device ownership mismatch")
        if device.token_state == TokenState.REVOKED.value:
            raise UnauthorizedError("Device revoked")

    async def create_notification(
        self,
        *,
        user_id: str,
        device_id: str,
        notification_type: str,
        title: str,
        summary: str,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationItem:
        item = NotificationItem(
            user_id=user_id,
            device_id=device_id,
            notification_type=notification_type,
            title=title.strip()[:255],
            summary=sanitize_notification_summary(summary),
            task_id=task_id,
            metadata_json=metadata,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_notifications(
        self, principal: Principal, *, limit: int = 50
    ) -> tuple[list[NotificationItem], int]:
        await self._validate_device(principal)
        result = await self.session.execute(
            select(NotificationItem)
            .where(
                NotificationItem.user_id == principal.user_id,
                NotificationItem.device_id == principal.device_id,
            )
            .order_by(NotificationItem.created_at.desc())
            .limit(limit)
        )
        items = list(result.scalars().all())
        unread_result = await self.session.execute(
            select(func.count())
            .select_from(NotificationItem)
            .where(
                NotificationItem.user_id == principal.user_id,
                NotificationItem.device_id == principal.device_id,
                NotificationItem.read_at.is_(None),
            )
        )
        unread = int(unread_result.scalar_one())
        return items, unread

    async def mark_read(self, principal: Principal, notification_id: str) -> NotificationItem:
        await self._validate_device(principal)
        result = await self.session.execute(
            select(NotificationItem).where(NotificationItem.id == notification_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise NotFoundError("notification", notification_id)
        if item.user_id != principal.user_id or item.device_id != principal.device_id:
            raise UnauthorizedError("Notification ownership mismatch")
        if item.read_at is None:
            item.read_at = _utc_now()
        await self.session.flush()
        return item

    async def mark_all_read(self, principal: Principal) -> int:
        await self._validate_device(principal)
        result = await self.session.execute(
            select(NotificationItem).where(
                NotificationItem.user_id == principal.user_id,
                NotificationItem.device_id == principal.device_id,
                NotificationItem.read_at.is_(None),
            )
        )
        now = _utc_now()
        count = 0
        for item in result.scalars().all():
            item.read_at = now
            count += 1
        await self.session.flush()
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or "unknown",
            action="notification.read_all",
            resource_type="notification",
            resource_id=None,
            details={"count": count},
        )
        return count

    async def unread_count(self, principal: Principal) -> int:
        if not principal.device_id:
            return 0
        result = await self.session.execute(
            select(func.count())
            .select_from(NotificationItem)
            .where(
                NotificationItem.user_id == principal.user_id,
                NotificationItem.device_id == principal.device_id,
                NotificationItem.read_at.is_(None),
            )
        )
        return int(result.scalar_one())
