"""Mission timeline and authenticated WebSocket event stream."""

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import authenticate_websocket, require_roles
from apps.api.deps import get_app_state, get_db_session
from apps.api.services.missions import MissionService
from nova_core.auth.principal import Principal
from nova_core.events.publisher import read_stream_events
from nova_core.models.database import get_session
from nova_core.schemas.api import TimelineEventResponse
from nova_core.schemas.settings import get_settings

router = APIRouter(tags=["missions"])


class TimelineListResponse(BaseModel):
    mission_id: str
    events: list[TimelineEventResponse]
    streaming: str
    after_sequence: int


class StreamingStatusResponse(BaseModel):
    redis: str
    streaming: str


@router.get("/missions/{mission_id}/timeline", response_model=TimelineListResponse)
async def get_mission_timeline(
    mission_id: str,
    principal: Annotated[Principal, Depends(require_roles("admin", "client"))],
    session: AsyncSession = Depends(get_db_session),
    after_sequence: int = Query(default=0, ge=0),
) -> TimelineListResponse:
    settings = get_settings()
    svc = MissionService(session, settings)
    await svc.get_mission(mission_id)
    events = await svc.get_timeline(mission_id, after_sequence=after_sequence)
    state = get_app_state()
    streaming = "live" if state.redis else "degraded"
    return TimelineListResponse(
        mission_id=mission_id,
        events=[
            TimelineEventResponse(
                id=e.id,
                event_type=e.event_type,
                agent_id=e.agent_id,
                message=e.message,
                payload=e.payload,
                created_at=e.created_at,
                sequence_number=e.sequence_number,
                stream_id=e.stream_id,
            )
            for e in events
        ],
        streaming=streaming,
        after_sequence=after_sequence,
    )


@router.get("/system/streaming-status", response_model=StreamingStatusResponse)
async def streaming_status(
    _principal: Annotated[Principal, Depends(require_roles("admin", "client"))],
) -> StreamingStatusResponse:
    state = get_app_state()
    if state.redis:
        try:
            await state.redis.ping()
            return StreamingStatusResponse(redis="ok", streaming="live")
        except Exception:
            return StreamingStatusResponse(redis="fail", streaming="degraded")
    return StreamingStatusResponse(redis="unavailable", streaming="degraded")


@router.websocket("/ws/missions/{mission_id}/events")
async def mission_events_ws(
    websocket: WebSocket,
    mission_id: str,
    after_sequence: int = Query(default=0),
) -> None:
    settings = get_settings()
    state = get_app_state()

    async for session in get_session():
        try:
            principal = await authenticate_websocket(websocket, session)
        except Exception:
            await websocket.close(code=4401, reason="Unauthorized")
            return
        if (
            principal.token_role != "client"
            or principal.websocket_scope != "mission_events"
            or principal.websocket_mission_id != mission_id
        ):
            await websocket.close(code=4403, reason="Ticket scope mismatch")
            return

        svc = MissionService(session, settings)
        try:
            await svc.get_mission(mission_id)
        except Exception:
            await websocket.close(code=4404, reason="Mission not found")
            return

        await websocket.accept()

        historical = await svc.get_timeline(mission_id, after_sequence=after_sequence)
        for event in historical:
            await websocket.send_json(_event_payload(event, mission_id))

        if state.redis:
            try:
                stream_events = await read_stream_events(
                    state.redis, mission_id, after_sequence=after_sequence
                )
                seen = {e.sequence_number for e in historical if e.sequence_number}
                for se in stream_events:
                    if se["sequence_number"] not in seen:
                        await websocket.send_json(
                            {
                                "event_type": se["event_type"],
                                "mission_id": mission_id,
                                "message": se["message"],
                                "payload": se["payload"],
                                "sequence_number": se["sequence_number"],
                                "stream_id": se.get("stream_id"),
                                "timestamp": se.get("timestamp"),
                                "streaming": "live",
                            }
                        )
            except Exception:
                await websocket.send_json(
                    {
                        "type": "streaming_status",
                        "status": "degraded",
                        "message": "Redis unavailable",
                    }
                )
        else:
            await websocket.send_json(
                {
                    "type": "streaming_status",
                    "status": "degraded",
                    "message": "Live streaming unavailable",
                }
            )

        subscribers = state.mission_event_subscribers.setdefault(mission_id, [])

        async def emit_live(event_type: str, mid: str, payload: dict[str, object] | None) -> None:
            msg = {
                "event_type": event_type,
                "mission_id": mid,
                "message": event_type,
                "payload": payload,
                "timestamp": datetime.now(UTC).isoformat(),
                "streaming": "live" if state.redis else "degraded",
            }
            try:
                await websocket.send_json(msg)
            except Exception:
                pass

        subscribers.append(emit_live)

        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
                elif data.startswith("{"):
                    cmd = json.loads(data)
                    if cmd.get("type") == "replay" and state.redis:
                        cursor = int(cmd.get("after_sequence", 0))
                        replayed = await read_stream_events(
                            state.redis, mission_id, after_sequence=cursor
                        )
                        for se in replayed:
                            await websocket.send_json(
                                {
                                    "event_type": se["event_type"],
                                    "mission_id": mission_id,
                                    "message": se["message"],
                                    "payload": se["payload"],
                                    "sequence_number": se["sequence_number"],
                                    "replay": True,
                                }
                            )
        except WebSocketDisconnect:
            pass
        finally:
            if emit_live in subscribers:
                subscribers.remove(emit_live)
        break


def _event_payload(event: Any, mission_id: str) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "mission_id": mission_id,
        "message": event.message,
        "payload": event.payload,
        "sequence_number": event.sequence_number,
        "stream_id": event.stream_id,
        "timestamp": event.created_at.isoformat() if event.created_at else None,
        "streaming": "durable",
    }
