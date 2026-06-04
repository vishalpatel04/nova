"""Core API route handlers."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import nova_core
from apps.api.auth import get_current_principal
from apps.api.deps import get_app_state, get_db_session
from apps.api.services.devices import DeviceService
from apps.api.services.missions import MissionService
from nova_core.auth.principal import Principal
from nova_core.devices.availability import get_worker_availability
from nova_core.models.enums import DeviceStatus, EvidenceBadge, MissionStatus, MissionStepStatus
from nova_core.models.orm import Agent, Mission
from nova_core.schemas.api import (
    AgentMessageResponse,
    AgentResponse,
    DeviceResponse,
    HealthResponse,
    MissionCreateRequest,
    MissionResponse,
    MissionStepResponse,
    ReadinessCheck,
    ReadinessResponse,
    SystemStatusResponse,
    TimelineEventResponse,
    WorkerHeartbeatRequest,
    WorkerRegisterRequest,
    WorkerRegisterResponse,
)
from nova_core.schemas.settings import Settings

router = APIRouter()


def _get_settings() -> Settings:
    return get_app_state().settings


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    settings = _get_settings()
    return HealthResponse(
        status="ok",
        version=nova_core.__version__,
        environment=settings.nova_env,
    )


@router.get("/ready", response_model=ReadinessResponse, tags=["system"])
@router.get("/readiness", response_model=ReadinessResponse, tags=["system"])
async def readiness(session: AsyncSession = Depends(get_db_session)) -> ReadinessResponse:
    checks: list[ReadinessCheck] = []
    all_ready = True

    try:
        await session.execute(select(func.now()))
        checks.append(ReadinessCheck(name="database", status="ok"))
    except Exception as exc:
        checks.append(ReadinessCheck(name="database", status="fail", detail=str(exc)))
        all_ready = False

    state = get_app_state()
    try:
        if state.redis:
            await state.redis.ping()
            checks.append(ReadinessCheck(name="redis", status="ok"))
        else:
            checks.append(ReadinessCheck(name="redis", status="degraded", detail="Not connected"))
    except Exception as exc:
        checks.append(ReadinessCheck(name="redis", status="fail", detail=str(exc)))
        all_ready = False

    return ReadinessResponse(ready=all_ready, checks=checks)


@router.get("/system/status", response_model=SystemStatusResponse, tags=["system"])
async def system_status(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> SystemStatusResponse:
    settings = _get_settings()
    availability = await get_worker_availability(session, settings)

    active_result = await session.execute(
        select(func.count())
        .select_from(Mission)
        .where(Mission.status == MissionStatus.RUNNING.value)
    )
    active_count = active_result.scalar() or 0

    db_status = "ok"
    redis_status = "ok"
    streaming = "degraded"
    state = get_app_state()
    try:
        await session.execute(select(func.now()))
    except Exception:
        db_status = "fail"
    try:
        if state.redis:
            await state.redis.ping()
            streaming = "live"
        else:
            redis_status = "unavailable"
    except Exception:
        redis_status = "fail"

    return SystemStatusResponse(
        control_plane="ok",
        database=db_status,
        redis=redis_status,
        streaming=streaming,
        workers_online=availability["workers_online"],
        workers_total=availability["workers_total"],
        workers_stale=availability["workers_stale"],
        workers_offline=availability["workers_offline"],
        workers_revoked=availability["workers_revoked"],
        has_eligible_online_worker=availability["has_eligible_online_worker"],
        missions_active=active_count,
        timestamp=datetime.now(UTC),
    )


@router.get("/devices", response_model=list[DeviceResponse], tags=["devices"])
async def list_devices(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> list[DeviceResponse]:
    settings = _get_settings()
    svc = DeviceService(session, settings)
    devices = await svc.list_devices()
    responses = []
    for d in devices:
        caps = await svc.get_device_capabilities(d.id)
        responses.append(
            DeviceResponse(
                id=d.id,
                name=d.name,
                device_type=d.device_type,
                status=DeviceStatus(d.status),
                hostname=d.hostname,
                os_version=d.os_version,
                architecture=d.architecture,
                privacy_class=d.privacy_class,
                token_state=d.token_state,
                connection_status=d.connection_status,
                last_seen_at=d.last_seen_at,
                capabilities=caps,
            )
        )
    return responses


@router.get("/agents", response_model=list[AgentResponse], tags=["agents"])
async def list_agents(
    _principal: Annotated[Principal, Depends(get_current_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> list[AgentResponse]:
    result = await session.execute(select(Agent).order_by(Agent.id))
    agents = result.scalars().all()
    return [
        AgentResponse(
            id=a.id,
            display_name=a.display_name,
            role=a.role,
            description=a.description,
            colour_token=a.colour_token,
            icon_token=a.icon_token,
            voice_profile_id=a.voice_profile_id,
            model_tier=a.model_tier,
            status=a.status,
            allowed_tool_categories=a.allowed_tool_categories or [],
        )
        for a in agents
    ]


@router.post("/missions", response_model=MissionResponse, status_code=201, tags=["missions"])
async def create_mission(
    body: MissionCreateRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: AsyncSession = Depends(get_db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> MissionResponse:
    settings = _get_settings()
    svc = MissionService(session, settings)
    svc.set_event_emitter(_publish_mission_event)
    mission = await svc.create_and_run(
        user_id=principal.user_id,
        mission_type=body.mission_type,
        title=body.title,
        request_payload=body.request_payload,
        idempotency_key=idempotency_key,
        principal=principal,
    )
    return _mission_to_response(mission)


@router.get("/missions/{mission_id}", response_model=MissionResponse, tags=["missions"])
async def get_mission(
    mission_id: str,
    _principal: Annotated[Principal, Depends(get_current_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> MissionResponse:
    settings = _get_settings()
    svc = MissionService(session, settings)
    mission = await svc.get_mission(mission_id)
    return _mission_to_response(mission)


@router.post("/workers/register", response_model=WorkerRegisterResponse, tags=["worker"])
async def register_worker(
    body: WorkerRegisterRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> WorkerRegisterResponse:
    settings = _get_settings()
    svc = DeviceService(session, settings)
    device = await svc.register_device(
        device_id=body.device_id,
        name=body.name,
        device_type=body.device_type,
        hostname=body.hostname,
        os_version=body.os_version,
        capabilities=body.capabilities,
        metadata=body.metadata,
    )
    return WorkerRegisterResponse(
        device_id=device.id,
        status="registered",
        message=f"Device '{device.name}' registered successfully",
    )


@router.post("/workers/heartbeat", tags=["worker"])
async def worker_heartbeat(
    body: WorkerHeartbeatRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    settings = _get_settings()
    svc = DeviceService(session, settings)
    device_id = principal.device_id or body.device_id
    await svc.record_heartbeat(
        device_id=device_id,
        status=body.status,
        payload=body.payload,
    )
    return {"status": "ok"}


def _mission_to_response(mission: Mission) -> MissionResponse:
    return MissionResponse(
        id=mission.id,
        mission_type=mission.mission_type,
        status=MissionStatus(mission.status),
        title=mission.title,
        request_payload=mission.request_payload,
        result_payload=mission.result_payload,
        error_message=mission.error_message,
        assigned_agent_id=mission.assigned_agent_id,
        created_at=mission.created_at,
        started_at=mission.started_at,
        completed_at=mission.completed_at,
        steps=[
            MissionStepResponse(
                id=s.id,
                step_order=s.step_order,
                name=s.name,
                status=MissionStepStatus(s.status),
                agent_id=s.agent_id,
                output_payload=s.output_payload,
            )
            for s in sorted(mission.steps, key=lambda x: x.step_order)
        ],
        timeline_events=[
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
            for e in mission.timeline_events
        ],
        agent_messages=[
            AgentMessageResponse(
                id=m.id,
                agent_id=m.agent_id,
                role=m.role,
                content=m.content,
                evidence_badge=EvidenceBadge(m.evidence_badge),
                created_at=m.created_at,
            )
            for m in mission.agent_messages
        ],
    )


async def _publish_mission_event(
    event_type: str, mission_id: str, payload: dict[str, object] | None
) -> None:
    subscribers = list(get_app_state().mission_event_subscribers.get(mission_id, []))
    for subscriber in subscribers:
        await subscriber(event_type, mission_id, payload)
