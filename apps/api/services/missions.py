"""Mission service — create, execute, queue, and query missions."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.deps import get_app_state
from apps.api.services.idempotency import IdempotencyService
from nova_core.auth.principal import Principal
from nova_core.devices.availability import get_worker_availability
from nova_core.events.publisher import publish_timeline_event
from nova_core.models.enums import MissionStatus, TimelineEventType
from nova_core.models.orm import Mission, QueuedMission, TimelineEvent
from nova_core.schemas.errors import ConflictError, NotFoundError, ValidationError
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
from nova_core.workflows.base import WorkflowContext
from nova_core.workflows.system_status import WORKFLOW_REGISTRY

WORKER_REQUIRED_MISSIONS = {"system_status"}


class MissionService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._event_emitter = None

    def set_event_emitter(self, emitter: Any) -> None:
        self._event_emitter = emitter

    async def create_mission(
        self,
        *,
        user_id: str,
        mission_type: str,
        title: str,
        request_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        principal: Principal | None = None,
    ) -> Mission:
        scope = f"POST:/missions:{mission_type}"
        principal_id = principal.idempotency_scope_id if principal else f"user:{user_id}"

        if idempotency_key:
            idem = IdempotencyService(self.session)
            existing_record = await idem.get_existing(
                principal_id=principal_id,
                scope=scope,
                idempotency_key=idempotency_key,
                request_body={
                    "mission_type": mission_type,
                    "title": title,
                    "request_payload": request_payload,
                },
            )
            if existing_record:
                mission = await self.get_mission(existing_record.resource_id)
                return mission

        if mission_type not in WORKFLOW_REGISTRY:
            raise ValidationError(
                f"Unknown mission type: {mission_type}",
                details={"supported": list(WORKFLOW_REGISTRY.keys())},
            )

        mission = Mission(
            user_id=user_id,
            mission_type=mission_type,
            title=title,
            request_payload=request_payload,
            idempotency_key=idempotency_key,
            assigned_agent_id="nova",
            status=MissionStatus.PENDING.value,
        )
        self.session.add(mission)
        await self.session.flush()

        if idempotency_key:
            idem = IdempotencyService(self.session)
            await idem.check_or_store(
                principal_id=principal_id,
                scope=scope,
                idempotency_key=idempotency_key,
                request_body={
                    "mission_type": mission_type,
                    "title": title,
                    "request_payload": request_payload,
                },
                resource_type="mission",
                resource_id=mission.id,
            )

        redis = get_app_state().redis
        await publish_timeline_event(
            self.session,
            redis,
            mission_id=mission.id,
            event_type=TimelineEventType.MISSION_CREATED.value,
            agent_id="nova",
            message=f"Mission '{title}' created",
            payload={"mission_type": mission_type},
        )

        await record_audit_event(
            self.session,
            actor_type=principal.principal_type if principal else "user",
            actor_id=principal.principal_id if principal else user_id,
            action="mission.created",
            resource_type="mission",
            resource_id=mission.id,
            details={"mission_type": mission_type, "title": title},
        )

        await self.session.commit()
        return mission

    async def execute_mission(self, mission_id: str) -> Mission:
        result = await self.session.execute(select(Mission).where(Mission.id == mission_id))
        mission = result.scalar_one_or_none()
        if not mission:
            raise NotFoundError("Mission", mission_id)

        if mission.status in (
            MissionStatus.COMPLETED.value,
            MissionStatus.CANCELLED.value,
        ):
            return mission

        if mission.status == MissionStatus.RUNNING.value:
            raise ConflictError("Mission is already running")

        if mission.status == MissionStatus.QUEUED_WAITING_FOR_WORKER.value:
            raise ConflictError("Mission is queued waiting for worker")

        workflow_cls = WORKFLOW_REGISTRY.get(mission.mission_type)
        if not workflow_cls:
            raise ValidationError(f"No workflow for type: {mission.mission_type}")

        workflow = workflow_cls()
        redis = get_app_state().redis

        async def emit(event_type: str, mid: str, payload: dict[str, Any] | None) -> None:
            await publish_timeline_event(
                self.session,
                redis,
                mission_id=mid,
                event_type=event_type,
                agent_id="nova",
                message=event_type,
                payload=payload,
            )
            if self._event_emitter:
                await self._event_emitter(event_type, mid, payload)

        ctx = WorkflowContext(
            session=self.session,
            settings=self.settings,
            mission=mission,
            emit_event=emit,
            redis=redis,
        )

        try:
            await workflow.run(ctx)
            await self.session.commit()
        except Exception:
            await self.session.commit()
            raise

        return mission

    async def get_mission(self, mission_id: str) -> Mission:
        result = await self.session.execute(
            select(Mission)
            .where(Mission.id == mission_id)
            .options(
                selectinload(Mission.steps),
                selectinload(Mission.timeline_events),
                selectinload(Mission.agent_messages),
            )
        )
        mission = result.scalar_one_or_none()
        if not mission:
            raise NotFoundError("Mission", mission_id)
        return mission

    async def _should_queue_for_worker(self, mission_type: str) -> bool:
        if mission_type not in WORKER_REQUIRED_MISSIONS:
            return False
        state = get_app_state()
        if state.worker_connections.has_eligible_worker():
            return False
        availability = await get_worker_availability(self.session, self.settings)
        return not availability["has_eligible_online_worker"]

    async def _queue_mission(self, mission: Mission) -> Mission:
        mission.status = MissionStatus.QUEUED_WAITING_FOR_WORKER.value
        message = (
            "No eligible worker is online. Your mission is queued and will start "
            "when an eligible worker reconnects."
        )
        redis = get_app_state().redis
        await publish_timeline_event(
            self.session,
            redis,
            mission_id=mission.id,
            event_type=TimelineEventType.MISSION_CREATED.value,
            agent_id="nova",
            message=message,
            payload={"queued": True, "reason": "worker_offline"},
        )
        self.session.add(
            QueuedMission(
                mission_id=mission.id,
                required_device_types=["macos_worker", "linux_worker", "cloud_worker"],
            )
        )
        await self.session.commit()
        return await self.get_mission(mission.id)

    async def create_and_run(
        self,
        *,
        user_id: str,
        mission_type: str,
        title: str,
        request_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        principal: Principal | None = None,
    ) -> Mission:
        mission = await self.create_mission(
            user_id=user_id,
            mission_type=mission_type,
            title=title,
            request_payload=request_payload,
            idempotency_key=idempotency_key,
            principal=principal,
        )
        if mission.status != MissionStatus.PENDING.value:
            return await self.get_mission(mission.id)

        if await self._should_queue_for_worker(mission_type):
            return await self._queue_mission(mission)

        mission = await self.execute_mission(mission.id)
        return await self.get_mission(mission.id)

    async def assign_queued_missions(self, device_id: str) -> list[dict[str, str]]:
        result = await self.session.execute(
            select(QueuedMission)
            .where(QueuedMission.acknowledged_at.is_(None))
            .order_by(QueuedMission.priority.desc(), QueuedMission.queued_at)
        )
        assigned: list[dict[str, str]] = []
        from datetime import UTC, datetime

        for queued in result.scalars().all():
            mission = await self.get_mission(queued.mission_id)
            if mission.status != MissionStatus.QUEUED_WAITING_FOR_WORKER.value:
                continue
            if queued.picked_up_by_device_id and queued.picked_up_by_device_id != device_id:
                continue
            if queued.picked_up_at is None:
                queued.picked_up_at = datetime.now(UTC)
                queued.picked_up_by_device_id = device_id
                queued.command_id = f"mission:{mission.id}:worker:{device_id}"
                await publish_timeline_event(
                    self.session,
                    get_app_state().redis,
                    mission_id=mission.id,
                    event_type=TimelineEventType.WORKER_HEARTBEAT.value,
                    agent_id="nova",
                    message="Mission assigned to worker and waiting for pickup acknowledgement",
                    payload={"device_id": device_id, "command_id": queued.command_id},
                )
            assigned.append({"mission_id": mission.id, "command_id": queued.command_id or ""})
        await self.session.commit()
        return assigned

    async def acknowledge_worker_pickup(
        self, *, device_id: str, mission_id: str, command_id: str
    ) -> Mission:
        result = await self.session.execute(
            select(QueuedMission).where(QueuedMission.mission_id == mission_id)
        )
        queued = result.scalar_one_or_none()
        if not queued:
            raise NotFoundError("QueuedMission", mission_id)
        if queued.command_id != command_id or queued.picked_up_by_device_id != device_id:
            raise ConflictError("Worker pickup acknowledgement does not match assignment")

        mission = await self.get_mission(mission_id)
        if queued.acknowledged_at is not None:
            return mission
        from datetime import UTC, datetime

        queued.acknowledged_at = datetime.now(UTC)
        mission.status = MissionStatus.RUNNING.value
        mission.started_at = datetime.now(UTC)
        await publish_timeline_event(
            self.session,
            get_app_state().redis,
            mission_id=mission.id,
            event_type=TimelineEventType.MISSION_STARTED.value,
            agent_id="nova",
            message="Worker acknowledged mission pickup",
            payload={"device_id": device_id, "command_id": command_id},
        )
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=device_id,
            action="worker.mission_pickup_acknowledged",
            resource_type="mission",
            resource_id=mission.id,
            details={"command_id": command_id},
        )
        await self.session.commit()
        return mission

    async def pickup_queued_missions(self, device_id: str) -> list[str]:
        assigned = await self.assign_queued_missions(device_id)
        return [item["mission_id"] for item in assigned]

    async def get_timeline(self, mission_id: str, after_sequence: int = 0) -> list[TimelineEvent]:
        result = await self.session.execute(
            select(TimelineEvent)
            .where(
                TimelineEvent.mission_id == mission_id,
                TimelineEvent.sequence_number > after_sequence,
            )
            .order_by(TimelineEvent.sequence_number)
        )
        return list(result.scalars().all())
