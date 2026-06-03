"""Mission service — create, execute, and query missions."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nova_core.models.enums import MissionStatus, TimelineEventType
from nova_core.models.orm import Mission, TimelineEvent
from nova_core.schemas.errors import ConflictError, NotFoundError, ValidationError
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
from nova_core.workflows.base import WorkflowContext
from nova_core.workflows.system_status import WORKFLOW_REGISTRY


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
    ) -> Mission:
        if idempotency_key:
            existing = await self.session.execute(
                select(Mission).where(Mission.idempotency_key == idempotency_key)
            )
            found = existing.scalar_one_or_none()
            if found:
                return found

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

        event = TimelineEvent(
            mission_id=mission.id,
            event_type=TimelineEventType.MISSION_CREATED.value,
            agent_id="nova",
            message=f"Mission '{title}' created",
            payload={"mission_type": mission_type},
        )
        self.session.add(event)

        await record_audit_event(
            self.session,
            actor_type="user",
            actor_id=user_id,
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

        workflow_cls = WORKFLOW_REGISTRY.get(mission.mission_type)
        if not workflow_cls:
            raise ValidationError(f"No workflow for type: {mission.mission_type}")

        workflow = workflow_cls()

        async def emit(event_type: str, mid: str, payload: dict[str, Any] | None) -> None:
            if self._event_emitter:
                await self._event_emitter(event_type, mid, payload)

        ctx = WorkflowContext(
            session=self.session,
            settings=self.settings,
            mission=mission,
            emit_event=emit,
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

    async def create_and_run(
        self,
        *,
        user_id: str,
        mission_type: str,
        title: str,
        request_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Mission:
        mission = await self.create_mission(
            user_id=user_id,
            mission_type=mission_type,
            title=title,
            request_payload=request_payload,
            idempotency_key=idempotency_key,
        )
        if mission.status == MissionStatus.PENDING.value:
            mission = await self.execute_mission(mission.id)
        return await self.get_mission(mission.id)
