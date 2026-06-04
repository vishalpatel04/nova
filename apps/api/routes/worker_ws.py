"""Worker WebSocket connection handler."""

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import authenticate_websocket
from apps.api.deps import get_app_state
from apps.api.services.devices import DeviceService
from apps.api.services.missions import MissionService
from nova_core.models.database import get_session
from nova_core.models.enums import ConnectionStatus, DeviceStatus
from nova_core.schemas.settings import get_settings
from nova_core.sentry.logging import get_logger

logger = get_logger("nova.worker_ws")

router = APIRouter(tags=["worker"])


@router.websocket("/ws/worker")
async def worker_websocket(websocket: WebSocket) -> None:
    settings = get_settings()
    state = get_app_state()

    async for session in get_session():
        try:
            principal = await authenticate_websocket(websocket, session)
        except Exception:
            await websocket.close(code=4401, reason="Unauthorized")
            return

        if principal.device_id is None:
            await websocket.close(code=4403, reason="Worker token required")
            return

        device_id = principal.device_id
        await websocket.accept()

        device_svc = DeviceService(session, settings)
        mission_svc = MissionService(session, settings)

        state.worker_connections.register(device_id, principal.device_type or "macos_worker")

        from sqlalchemy import select

        from nova_core.models.orm import Device

        device_result = await session.execute(select(Device).where(Device.id == device_id))
        device = device_result.scalar_one_or_none()
        if device:
            device.connection_status = ConnectionStatus.CONNECTED.value
            device.status = DeviceStatus.ONLINE.value
            device.last_seen_at = datetime.now(UTC)
            await session.commit()

        await websocket.send_json({"type": "connected", "device_id": device_id})

        picked = await mission_svc.pickup_queued_missions(device_id)
        if picked:
            await websocket.send_json({"type": "missions_assigned", "mission_ids": picked})

        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                await _handle_worker_message(
                    websocket, session, device_svc, mission_svc, device_id, msg, state
                )
        except WebSocketDisconnect:
            logger.info("worker_disconnected", device_id=device_id)
        finally:
            state.worker_connections.disconnect(device_id)
            if device:
                device.connection_status = ConnectionStatus.DISCONNECTED.value
                await session.commit()
        break


async def _handle_worker_message(
    websocket: WebSocket,
    session: AsyncSession,
    device_svc: DeviceService,
    mission_svc: MissionService,
    device_id: str,
    msg: dict[str, Any],
    state: Any,
) -> None:
    msg_type = msg.get("type")

    if msg_type == "register":
        await device_svc.register_device(
            device_id=device_id,
            name=msg.get("name", device_id),
            device_type=msg.get("device_type", "macos_worker"),
            hostname=msg.get("hostname"),
            os_version=msg.get("os_version"),
            architecture=msg.get("architecture"),
            capabilities=msg.get("capabilities", []),
            metadata=msg.get("metadata"),
        )
        state.worker_connections.register(
            device_id, msg.get("device_type", "macos_worker"), msg.get("capabilities")
        )
        await websocket.send_json({"type": "registered", "device_id": device_id})

    elif msg_type == "heartbeat":
        payload = msg.get("payload", {})
        await device_svc.record_heartbeat(device_id=device_id, payload=payload)
        state.worker_connections.heartbeat(device_id, payload)
        await websocket.send_json(
            {"type": "heartbeat_ack", "timestamp": datetime.now(UTC).isoformat()}
        )

    elif msg_type == "status":
        state.worker_connections.heartbeat(device_id, msg.get("payload"))
        await websocket.send_json({"type": "status_ack"})

    elif msg_type == "ping":
        await websocket.send_json({"type": "pong"})

    else:
        await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})
