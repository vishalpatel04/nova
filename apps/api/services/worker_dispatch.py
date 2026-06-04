"""Worker command dispatch — PostgreSQL authority, Redis Streams transport."""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import get_app_state
from nova_core.events.publisher import publish_timeline_event
from nova_core.models.enums import (
    MissionStatus,
    TimelineEventType,
    WorkerCommandRouting,
    WorkerCommandStatus,
)
from nova_core.models.orm import Device, Mission, QueuedMission, WorkerCommandAssignment
from nova_core.schemas.errors import ConflictError, NotFoundError, ValidationError
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
from nova_core.utils.time import ensure_utc, utc_now
from nova_core.worker_dispatch.commands import (
    MISSION_COMMAND_MAP,
    READ_ONLY_COMMAND_TYPES,
)
from nova_core.worker_dispatch.streams import (
    class_stream_key,
    device_stream_key,
    write_command,
)

WORKER_CLASSES = ("macos_worker", "linux_worker", "cloud_worker")


class WorkerDispatchService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._policies = settings.load_yaml("policies.yaml")

    def _dispatch_policy(self) -> dict[str, Any]:
        dispatch = self._policies.get("worker_dispatch", {})
        return dispatch if isinstance(dispatch, dict) else {}

    def _stale_seconds(self) -> int:
        return int(self._dispatch_policy().get("stale_assignment_seconds", 300))

    def _max_attempts(self) -> int:
        return int(self._dispatch_policy().get("max_command_attempts", 3))

    def _stream_max_len(self) -> int:
        events = self._policies.get("events", {})
        if isinstance(events, dict):
            return int(events.get("redis_stream_max_len", 10000))
        return 10000

    @staticmethod
    def mission_command_id(mission_id: str, device_id: str | None = None) -> str:
        if device_id:
            return f"mission:{mission_id}:worker:{device_id}"
        return f"mission:{mission_id}:class"

    async def create_mission_command(
        self,
        *,
        mission_id: str,
        mission_type: str,
        required_device_types: list[str] | None = None,
        target_device_id: str | None = None,
    ) -> WorkerCommandAssignment:
        command_type = MISSION_COMMAND_MAP.get(mission_type)
        if not command_type or command_type not in READ_ONLY_COMMAND_TYPES:
            raise ValidationError(f"No worker command mapping for mission type: {mission_type}")

        command_id = self.mission_command_id(mission_id, target_device_id)
        existing = await self.session.execute(
            select(WorkerCommandAssignment).where(WorkerCommandAssignment.command_id == command_id)
        )
        row = existing.scalar_one_or_none()
        if row:
            return row

        worker_class = (required_device_types or list(WORKER_CLASSES))[0]
        routing = (
            WorkerCommandRouting.DEVICE.value
            if target_device_id
            else WorkerCommandRouting.WORKER_CLASS.value
        )
        target_class = worker_class if routing == WorkerCommandRouting.WORKER_CLASS.value else None
        assignment = WorkerCommandAssignment(
            command_id=command_id,
            mission_id=mission_id,
            command_type=command_type,
            routing_mode=routing,
            target_device_id=target_device_id,
            target_worker_class=target_class,
            status=WorkerCommandStatus.PENDING.value,
            payload={"mission_type": mission_type},
            max_attempts=self._max_attempts(),
        )
        self.session.add(assignment)
        await self.session.flush()
        await record_audit_event(
            self.session,
            actor_type="system",
            actor_id="nova",
            action="worker_command.created",
            resource_type="worker_command",
            resource_id=command_id,
            details={"mission_id": mission_id, "command_type": command_type},
        )
        return assignment

    def _stream_for(self, assignment: WorkerCommandAssignment) -> str:
        if assignment.routing_mode == WorkerCommandRouting.DEVICE.value:
            device_id = assignment.target_device_id or assignment.assigned_device_id
            if not device_id:
                raise ValidationError("Device routing requires target_device_id")
            return device_stream_key(device_id)
        worker_class = assignment.target_worker_class or "macos_worker"
        return class_stream_key(worker_class)

    async def dispatch_assignment(
        self, assignment: WorkerCommandAssignment, *, device_id: str | None = None
    ) -> WorkerCommandAssignment:
        if assignment.status in (
            WorkerCommandStatus.COMPLETED.value,
            WorkerCommandStatus.CANCELLED.value,
        ):
            return assignment

        redis = get_app_state().redis
        stream_key = self._stream_for(assignment)
        if device_id and assignment.routing_mode == WorkerCommandRouting.WORKER_CLASS.value:
            assignment.assigned_device_id = device_id

        entry_id = None
        if redis is not None:
            entry_id = await write_command(
                redis,
                stream_key,
                command_id=assignment.command_id,
                command_type=assignment.command_type,
                mission_id=assignment.mission_id,
                payload=assignment.payload,
                max_len=self._stream_max_len(),
            )

        assignment.stream_key = stream_key
        assignment.stream_entry_id = entry_id
        assignment.status = WorkerCommandStatus.DISPATCHED.value
        assignment.dispatched_at = utc_now()
        assignment.attempt_count += 1

        if assignment.mission_id:
            await publish_timeline_event(
                self.session,
                redis,
                mission_id=assignment.mission_id,
                event_type=TimelineEventType.WORKER_COMMAND_DISPATCHED.value,
                agent_id="nova",
                message="Worker command dispatched to stream",
                payload={
                    "command_id": assignment.command_id,
                    "stream_key": stream_key,
                    "stream_entry_id": entry_id,
                    "streaming": "live" if entry_id else "degraded",
                },
            )
        await record_audit_event(
            self.session,
            actor_type="system",
            actor_id="nova",
            action="worker_command.dispatched",
            resource_type="worker_command",
            resource_id=assignment.command_id,
            details={"stream_key": stream_key, "device_id": device_id},
        )
        await self.session.flush()
        return assignment

    async def recover_stale_assignments(self) -> list[str]:
        stale_seconds = self._stale_seconds()
        cutoff = utc_now() - timedelta(seconds=stale_seconds)
        result = await self.session.execute(
            select(WorkerCommandAssignment).where(
                WorkerCommandAssignment.status.in_(
                    (
                        WorkerCommandStatus.DISPATCHED.value,
                        WorkerCommandStatus.PICKED_UP.value,
                    )
                )
            )
        )
        recovered: list[str] = []
        for assignment in result.scalars().all():
            ts = assignment.picked_up_at or assignment.dispatched_at
            if ts is None or ensure_utc(ts) > cutoff:
                continue
            if assignment.attempt_count >= assignment.max_attempts:
                assignment.status = WorkerCommandStatus.FAILED.value
                assignment.last_error = "max attempts exceeded after stale recovery"
                assignment.completed_at = utc_now()
                recovered.append(assignment.command_id)
                continue
            assignment.status = WorkerCommandStatus.STALE_RECOVERED.value
            assignment.picked_up_at = None
            assignment.dispatched_at = None
            assignment.stream_entry_id = None
            assignment.assigned_device_id = None
            assignment.status = WorkerCommandStatus.PENDING.value
            recovered.append(assignment.command_id)
            await record_audit_event(
                self.session,
                actor_type="system",
                actor_id="nova",
                action="worker_command.stale_recovered",
                resource_type="worker_command",
                resource_id=assignment.command_id,
            )
        if recovered:
            await self.session.flush()
        return recovered

    async def pending_commands_for_worker(
        self, device_id: str, device_type: str
    ) -> list[dict[str, str]]:
        await self.recover_stale_assignments()

        device_result = await self.session.execute(select(Device).where(Device.id == device_id))
        device = device_result.scalar_one_or_none()
        if device and device.status == "revoked":
            return []

        result = await self.session.execute(
            select(WorkerCommandAssignment).where(
                WorkerCommandAssignment.status.in_(
                    (
                        WorkerCommandStatus.PENDING.value,
                        WorkerCommandStatus.DISPATCHED.value,
                        WorkerCommandStatus.STALE_RECOVERED.value,
                    )
                )
            )
        )
        commands: list[dict[str, str]] = []
        for assignment in result.scalars().all():
            if not self._matches_worker(assignment, device_id, device_type):
                continue
            if assignment.status == WorkerCommandStatus.PENDING.value:
                await self.dispatch_assignment(assignment, device_id=device_id)
            elif assignment.routing_mode == WorkerCommandRouting.WORKER_CLASS.value:
                if assignment.assigned_device_id is None:
                    assignment.assigned_device_id = device_id
                    await self.session.flush()
                elif assignment.assigned_device_id != device_id:
                    continue
            commands.append(
                {
                    "command_id": assignment.command_id,
                    "command_type": assignment.command_type,
                    "mission_id": assignment.mission_id or "",
                    "stream_key": assignment.stream_key or "",
                }
            )
        await self.session.commit()
        return commands

    def _matches_worker(
        self, assignment: WorkerCommandAssignment, device_id: str, device_type: str
    ) -> bool:
        if assignment.routing_mode == WorkerCommandRouting.DEVICE.value:
            return assignment.target_device_id == device_id
        if assignment.target_worker_class:
            return assignment.target_worker_class == device_type
        return device_type in WORKER_CLASSES

    async def acknowledge_pickup(
        self, *, device_id: str, command_id: str
    ) -> WorkerCommandAssignment:
        result = await self.session.execute(
            select(WorkerCommandAssignment).where(WorkerCommandAssignment.command_id == command_id)
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            raise NotFoundError("WorkerCommand", command_id)

        device_result = await self.session.execute(select(Device).where(Device.id == device_id))
        device = device_result.scalar_one_or_none()
        if device and device.status == "revoked":
            raise ConflictError("Revoked worker cannot accept commands")

        if assignment.routing_mode == WorkerCommandRouting.DEVICE.value:
            if assignment.target_device_id != device_id:
                raise ConflictError("Command routed to a different device")
        elif assignment.assigned_device_id and assignment.assigned_device_id != device_id:
            raise ConflictError("Command already assigned to another worker")

        if assignment.status == WorkerCommandStatus.PICKED_UP.value:
            if assignment.assigned_device_id == device_id:
                return assignment
            raise ConflictError("Command already picked up by another worker")

        if assignment.status in (
            WorkerCommandStatus.COMPLETED.value,
            WorkerCommandStatus.FAILED.value,
            WorkerCommandStatus.CANCELLED.value,
        ):
            return assignment

        assignment.status = WorkerCommandStatus.PICKED_UP.value
        assignment.picked_up_at = utc_now()
        assignment.assigned_device_id = device_id

        if assignment.mission_id:
            queued_result = await self.session.execute(
                select(QueuedMission).where(QueuedMission.mission_id == assignment.mission_id)
            )
            queued = queued_result.scalar_one_or_none()
            if queued:
                queued.picked_up_at = assignment.picked_up_at
                queued.picked_up_by_device_id = device_id
                queued.command_id = command_id
                queued.acknowledged_at = assignment.picked_up_at

            mission_result = await self.session.execute(
                select(Mission).where(Mission.id == assignment.mission_id)
            )
            mission = mission_result.scalar_one_or_none()
            if mission and mission.status == MissionStatus.QUEUED_WAITING_FOR_WORKER.value:
                mission.status = MissionStatus.RUNNING.value
                mission.started_at = assignment.picked_up_at

            await publish_timeline_event(
                self.session,
                get_app_state().redis,
                mission_id=assignment.mission_id,
                event_type=TimelineEventType.WORKER_COMMAND_PICKED_UP.value,
                agent_id="nova",
                message="Worker acknowledged command pickup",
                payload={"command_id": command_id, "device_id": device_id},
            )

        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=device_id,
            action="worker_command.picked_up",
            resource_type="worker_command",
            resource_id=command_id,
        )
        await self.session.commit()
        return assignment

    async def record_result(
        self,
        *,
        device_id: str,
        command_id: str,
        success: bool,
        result_payload: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> WorkerCommandAssignment:
        result = await self.session.execute(
            select(WorkerCommandAssignment).where(WorkerCommandAssignment.command_id == command_id)
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            raise NotFoundError("WorkerCommand", command_id)

        if assignment.assigned_device_id and assignment.assigned_device_id != device_id:
            raise ConflictError("Command result from non-assigned worker")

        if assignment.status == WorkerCommandStatus.COMPLETED.value:
            return assignment

        if assignment.status == WorkerCommandStatus.FAILED.value and not success:
            return assignment

        assignment.completed_at = utc_now()
        assignment.result_payload = result_payload
        if success:
            assignment.status = WorkerCommandStatus.COMPLETED.value
            event_type = TimelineEventType.WORKER_COMMAND_COMPLETED.value
            message = "Worker command completed"
            audit_action = "worker_command.completed"
        else:
            assignment.status = WorkerCommandStatus.FAILED.value
            assignment.last_error = error_message
            event_type = TimelineEventType.WORKER_COMMAND_FAILED.value
            message = error_message or "Worker command failed"
            audit_action = "worker_command.failed"

        if assignment.mission_id:
            await publish_timeline_event(
                self.session,
                get_app_state().redis,
                mission_id=assignment.mission_id,
                event_type=event_type,
                agent_id="nova",
                message=message,
                payload={"command_id": command_id, "result": result_payload},
            )
            if success:
                await self._complete_mission_from_result(assignment)

        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=device_id,
            action=audit_action,
            resource_type="worker_command",
            resource_id=command_id,
            details={"success": success},
        )
        await self.session.commit()
        return assignment

    async def _complete_mission_from_result(self, assignment: WorkerCommandAssignment) -> None:
        if not assignment.mission_id:
            return
        result = await self.session.execute(
            select(Mission).where(Mission.id == assignment.mission_id)
        )
        mission = result.scalar_one_or_none()
        if not mission:
            raise NotFoundError("Mission", assignment.mission_id)
        if mission.status in (
            MissionStatus.COMPLETED.value,
            MissionStatus.FAILED.value,
        ):
            return

        now = utc_now()
        if mission.started_at is None:
            mission.started_at = assignment.picked_up_at or now
        mission.status = MissionStatus.COMPLETED.value
        mission.result_payload = assignment.result_payload
        mission.completed_at = now
        await publish_timeline_event(
            self.session,
            get_app_state().redis,
            mission_id=mission.id,
            event_type=TimelineEventType.MISSION_COMPLETED.value,
            agent_id="nova",
            message=f"Mission '{mission.title}' completed by worker",
            payload={"command_id": assignment.command_id, "result": assignment.result_payload},
        )
        await self.session.flush()

    async def release_assignments_for_revoked_device(self, device_id: str) -> None:
        result = await self.session.execute(
            select(WorkerCommandAssignment).where(
                WorkerCommandAssignment.assigned_device_id == device_id,
                WorkerCommandAssignment.status.in_(
                    (
                        WorkerCommandStatus.DISPATCHED.value,
                        WorkerCommandStatus.PICKED_UP.value,
                        WorkerCommandStatus.PENDING.value,
                    )
                ),
            )
        )
        for assignment in result.scalars().all():
            assignment.status = WorkerCommandStatus.PENDING.value
            assignment.assigned_device_id = None
            assignment.picked_up_at = None
            assignment.dispatched_at = None
            assignment.stream_entry_id = None
            if assignment.routing_mode == WorkerCommandRouting.DEVICE.value:
                assignment.status = WorkerCommandStatus.CANCELLED.value

        queued_result = await self.session.execute(
            select(QueuedMission).where(QueuedMission.picked_up_by_device_id == device_id)
        )
        for queued in queued_result.scalars().all():
            if queued.acknowledged_at is None:
                queued.picked_up_at = None
                queued.picked_up_by_device_id = None
                queued.command_id = None
        await self.session.flush()
