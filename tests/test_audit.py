"""Audit event tests."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.devices import DeviceService
from apps.api.services.missions import MissionService
from apps.api.services.seed import seed_agents
from nova_core.models.orm import AuditEvent
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event


@pytest.mark.asyncio
async def test_record_audit_event(db_session: AsyncSession) -> None:
    event = await record_audit_event(
        db_session,
        actor_type="user",
        actor_id="arth",
        action="test.action",
        resource_type="test",
        resource_id="123",
        details={"key": "value"},
    )
    await db_session.commit()
    assert event.id is not None
    assert event.action == "test.action"


@pytest.mark.asyncio
async def test_mission_creates_audit_event(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    await seed_agents(db_session, test_settings)
    svc = MissionService(db_session, test_settings)
    await svc.create_and_run(
        user_id="arth",
        mission_type="system_status",
        title="Audit test",
    )

    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "mission.created")
    )
    events = list(result.scalars().all())
    assert len(events) >= 1


@pytest.mark.asyncio
async def test_device_registration_creates_audit_event(
    db_session: AsyncSession, test_settings: Settings
) -> None:
    svc = DeviceService(db_session, test_settings)
    await svc.register_device(
        device_id="audit-test-device",
        name="Audit Device",
        device_type="macos_worker",
    )

    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "device.registered")
    )
    events = list(result.scalars().all())
    assert len(events) >= 1
