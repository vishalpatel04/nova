"""Device availability and heartbeat utilities."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.enums import DeviceStatus
from nova_core.models.orm import Device, DeviceHeartbeat


async def get_worker_availability(
    session: AsyncSession,
    stale_threshold_seconds: int = 90,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    threshold = now - timedelta(seconds=stale_threshold_seconds)

    result = await session.execute(
        select(Device).where(
            Device.device_type.in_(["macos_worker", "linux_worker", "cloud_worker"])
        )
    )
    workers = list(result.scalars().all())

    online = 0
    stale = 0
    offline = 0
    worker_details: list[dict[str, Any]] = []

    for worker in workers:
        hb_result = await session.execute(
            select(DeviceHeartbeat)
            .where(DeviceHeartbeat.device_id == worker.id)
            .order_by(DeviceHeartbeat.recorded_at.desc())
            .limit(1)
        )
        latest_hb = hb_result.scalar_one_or_none()

        if latest_hb and latest_hb.recorded_at >= threshold:
            status = DeviceStatus.ONLINE
            online += 1
        elif latest_hb:
            status = DeviceStatus.STALE
            stale += 1
        else:
            status = DeviceStatus.OFFLINE
            offline += 1

        worker_details.append(
            {
                "device_id": worker.id,
                "name": worker.name,
                "device_type": worker.device_type,
                "status": status.value,
                "last_heartbeat": latest_hb.recorded_at.isoformat() if latest_hb else None,
            }
        )

    return {
        "workers_total": len(workers),
        "workers_online": online,
        "workers_stale": stale,
        "workers_offline": offline,
        "workers": worker_details,
        "checked_at": now.isoformat(),
    }
