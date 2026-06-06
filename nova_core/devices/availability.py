"""Device availability with policy-driven thresholds and revoked detection."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.enums import DeviceStatus
from nova_core.models.orm import Device, DeviceHeartbeat
from nova_core.schemas.settings import Settings
from nova_core.utils.time import ensure_utc, utc_now

WORKER_DEVICE_TYPES = ["macos_worker", "linux_worker", "cloud_worker", "friend_laptop"]


def _thresholds(settings: Settings) -> tuple[int, int]:
    policies = settings.load_yaml("policies.yaml")
    worker = policies.get("worker", {})
    if not isinstance(worker, dict):
        return 90, 300
    stale = int(worker.get("stale_heartbeat_threshold_seconds", 90))
    offline = int(worker.get("offline_heartbeat_threshold_seconds", 300))
    return stale, offline


def classify_device(
    device: Device,
    latest_hb: DeviceHeartbeat | None,
    now: datetime,
    stale_seconds: int,
    offline_seconds: int,
) -> DeviceStatus:
    if device.status == DeviceStatus.REVOKED.value:
        return DeviceStatus.REVOKED
    if device.token_state == "revoked":
        return DeviceStatus.REVOKED
    if device.connection_status == "connected":
        return DeviceStatus.ONLINE
    if latest_hb is None:
        return DeviceStatus.OFFLINE
    age = (now - ensure_utc(latest_hb.recorded_at)).total_seconds()
    if age <= stale_seconds:
        return DeviceStatus.ONLINE
    if age <= offline_seconds:
        return DeviceStatus.STALE
    return DeviceStatus.OFFLINE


async def get_worker_availability(
    session: AsyncSession,
    settings: Settings | None = None,
    stale_threshold_seconds: int | None = None,
) -> dict[str, Any]:
    if settings:
        stale_seconds, offline_seconds = _thresholds(settings)
    else:
        stale_seconds = stale_threshold_seconds or 90
        offline_seconds = stale_threshold_seconds or 300

    now = utc_now()

    result = await session.execute(
        select(Device).where(Device.device_type.in_(WORKER_DEVICE_TYPES))
    )
    workers = list(result.scalars().all())

    online = 0
    stale = 0
    offline = 0
    revoked = 0
    worker_details: list[dict[str, Any]] = []
    has_eligible_online = False

    for worker in workers:
        if worker.status == DeviceStatus.REVOKED.value:
            revoked += 1
            worker_details.append(
                {
                    "device_id": worker.id,
                    "name": worker.name,
                    "device_type": worker.device_type,
                    "status": DeviceStatus.REVOKED.value,
                    "last_heartbeat": None,
                }
            )
            continue

        hb_result = await session.execute(
            select(DeviceHeartbeat)
            .where(DeviceHeartbeat.device_id == worker.id)
            .order_by(DeviceHeartbeat.recorded_at.desc())
            .limit(1)
        )
        latest_hb = hb_result.scalar_one_or_none()
        status = classify_device(worker, latest_hb, now, stale_seconds, offline_seconds)

        if status == DeviceStatus.ONLINE:
            online += 1
            if worker.device_type in ("macos_worker", "linux_worker", "cloud_worker"):
                has_eligible_online = True
        elif status == DeviceStatus.STALE:
            stale += 1
        else:
            offline += 1

        worker_details.append(
            {
                "device_id": worker.id,
                "name": worker.name,
                "device_type": worker.device_type,
                "status": status.value,
                "connection_status": worker.connection_status,
                "last_heartbeat": latest_hb.recorded_at.isoformat() if latest_hb else None,
                "hostname": worker.hostname,
                "architecture": worker.architecture,
            }
        )

    return {
        "workers_total": len(workers),
        "workers_online": online,
        "workers_stale": stale,
        "workers_offline": offline,
        "workers_revoked": revoked,
        "has_eligible_online_worker": has_eligible_online,
        "workers": worker_details,
        "checked_at": now.isoformat(),
    }
