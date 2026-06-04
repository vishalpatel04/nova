"""Companion device inbox service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.auth.principal import Principal
from nova_core.models.enums import TokenState
from nova_core.models.orm import CompanionInboxItem, Device
from nova_core.schemas.errors import NotFoundError, UnauthorizedError, ValidationError
from nova_core.utils.time import utc_now


class CompanionInboxService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def validate_target_device(self, principal: Principal, target_device_id: str) -> Device:
        result = await self.session.execute(select(Device).where(Device.id == target_device_id))
        target = result.scalar_one_or_none()
        if target is None:
            raise NotFoundError("Device", target_device_id)
        if target.user_id != principal.user_id:
            raise UnauthorizedError("Target device is not owned by this user")
        if target.token_state == TokenState.REVOKED.value:
            raise UnauthorizedError("Target device is revoked")
        return target

    async def enqueue_prompt(
        self,
        principal: Principal,
        *,
        message: str,
        target_device_id: str,
        session_id: str | None = None,
        message_id: str | None = None,
    ) -> CompanionInboxItem:
        await self.validate_target_device(principal, target_device_id)
        item = CompanionInboxItem(
            user_id=principal.user_id,
            source_device_id=principal.device_id,
            target_device_id=target_device_id,
            message=message,
            status="pending",
            session_id=session_id,
            message_id=message_id,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_inbox(
        self,
        principal: Principal,
        *,
        device_id: str | None = None,
        limit: int = 50,
    ) -> list[CompanionInboxItem]:
        target_id = device_id or principal.device_id
        if not target_id:
            raise ValidationError("device_id is required for companion inbox")
        await self.validate_target_device(principal, target_id)
        result = await self.session.execute(
            select(CompanionInboxItem)
            .where(
                CompanionInboxItem.user_id == principal.user_id,
                CompanionInboxItem.target_device_id == target_id,
            )
            .order_by(CompanionInboxItem.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_delivered(self, principal: Principal, item_id: str) -> CompanionInboxItem:
        item = await self._get_owned_item(principal, item_id)
        if item.status == "pending":
            item.status = "delivered"
            item.delivered_at = utc_now()
        await self.session.flush()
        return item

    async def mark_read(self, principal: Principal, item_id: str) -> CompanionInboxItem:
        item = await self._get_owned_item(principal, item_id)
        if item.status in {"pending", "delivered"}:
            item.status = "read"
            if item.delivered_at is None:
                item.delivered_at = utc_now()
            item.read_at = utc_now()
        await self.session.flush()
        return item

    async def _get_owned_item(self, principal: Principal, item_id: str) -> CompanionInboxItem:
        result = await self.session.execute(
            select(CompanionInboxItem).where(
                CompanionInboxItem.id == item_id,
                CompanionInboxItem.user_id == principal.user_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise NotFoundError("CompanionInboxItem", item_id)
        if principal.device_id and item.target_device_id != principal.device_id:
            raise UnauthorizedError("Inbox item is not for this device")
        return item
