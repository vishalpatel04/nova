"""Device and worker registration service."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.enums import DeviceStatus
from nova_core.models.orm import Device, DeviceCapabilityRecord, DeviceHeartbeat, User
from nova_core.schemas.errors import NotFoundError
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event


class DeviceService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def ensure_default_user(self) -> User:
        result = await self.session.execute(
            select(User).where(User.id == self.settings.nova_default_user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                id=self.settings.nova_default_user_id,
                display_name="Arth Agrawal",
                email="arth@nova.local",
            )
            self.session.add(user)
            await self.session.flush()
        return user

    async def register_device(
        self,
        *,
        device_id: str,
        name: str,
        device_type: str,
        hostname: str | None = None,
        os_version: str | None = None,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Device:
        user = await self.ensure_default_user()

        result = await self.session.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()

        if device:
            device.name = name
            device.device_type = device_type
            device.hostname = hostname
            device.os_version = os_version
            device.status = DeviceStatus.REGISTERED.value
            device.metadata_json = metadata
        else:
            device = Device(
                id=device_id,
                user_id=user.id,
                name=name,
                device_type=device_type,
                hostname=hostname,
                os_version=os_version,
                status=DeviceStatus.REGISTERED.value,
                metadata_json=metadata,
            )
            self.session.add(device)

        await self.session.flush()

        if capabilities:
            for cap in capabilities:
                cap_result = await self.session.execute(
                    select(DeviceCapabilityRecord).where(
                        DeviceCapabilityRecord.device_id == device_id,
                        DeviceCapabilityRecord.capability == cap,
                    )
                )
                existing_cap = cap_result.scalar_one_or_none()
                if existing_cap:
                    existing_cap.enabled = True
                    existing_cap.reported_at = datetime.now(UTC)
                else:
                    self.session.add(
                        DeviceCapabilityRecord(
                            device_id=device_id,
                            capability=cap,
                            enabled=True,
                        )
                    )

        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=device_id,
            action="device.registered",
            resource_type="device",
            resource_id=device_id,
            details={"name": name, "device_type": device_type},
        )

        await self.session.commit()
        return device

    async def record_heartbeat(
        self,
        *,
        device_id: str,
        status: str = "online",
        payload: dict[str, Any] | None = None,
    ) -> DeviceHeartbeat:
        result = await self.session.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if not device:
            raise NotFoundError("Device", device_id)

        now = datetime.now(UTC)
        device.status = DeviceStatus.ONLINE.value
        device.last_seen_at = now

        heartbeat = DeviceHeartbeat(
            device_id=device_id,
            status=status,
            payload=payload,
        )
        self.session.add(heartbeat)
        await self.session.commit()
        return heartbeat

    async def list_devices(self) -> list[Device]:
        result = await self.session.execute(select(Device).order_by(Device.registered_at))
        return list(result.scalars().all())

    async def get_device_capabilities(self, device_id: str) -> list[str]:
        result = await self.session.execute(
            select(DeviceCapabilityRecord).where(
                DeviceCapabilityRecord.device_id == device_id,
                DeviceCapabilityRecord.enabled.is_(True),
            )
        )
        return [c.capability for c in result.scalars().all()]
