"""LangGraph-ready workflow interface — lightweight runner for Slice 1."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.enums import MissionStatus, MissionStepStatus, TimelineEventType
from nova_core.models.orm import AgentMessage, Mission, MissionStep, TimelineEvent
from nova_core.schemas.settings import Settings

MissionEventEmitter = Callable[[str, str, dict[str, Any] | None], Awaitable[None]]


@dataclass
class WorkflowContext:
    session: AsyncSession
    settings: Settings
    mission: Mission
    emit_event: MissionEventEmitter | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStepDefinition:
    name: str
    agent_id: str
    handler: Callable[[WorkflowContext], Awaitable[dict[str, Any] | None]]


class BaseWorkflow(ABC):
    mission_type: str

    @abstractmethod
    def steps(self) -> list[WorkflowStepDefinition]: ...

    async def run(self, ctx: WorkflowContext) -> dict[str, Any]:
        mission = ctx.mission
        mission.status = MissionStatus.RUNNING.value
        mission.started_at = datetime.now(UTC)
        await self._add_timeline(
            ctx,
            TimelineEventType.MISSION_STARTED,
            "nova",
            f"Mission '{mission.title}' started",
        )
        if ctx.emit_event:
            await ctx.emit_event("mission_started", mission.id, {"title": mission.title})

        results: dict[str, Any] = {}
        step_defs = self.steps()

        for order, step_def in enumerate(step_defs, start=1):
            step = MissionStep(
                mission_id=mission.id,
                step_order=order,
                name=step_def.name,
                status=MissionStepStatus.RUNNING.value,
                agent_id=step_def.agent_id,
                started_at=datetime.now(UTC),
            )
            ctx.session.add(step)
            await ctx.session.flush()

            await self._add_timeline(
                ctx,
                TimelineEventType.STEP_STARTED,
                step_def.agent_id,
                f"Step '{step_def.name}' started",
                {"step_id": step.id},
            )
            if ctx.emit_event:
                await ctx.emit_event(
                    "step_started",
                    mission.id,
                    {"step": step_def.name, "agent_id": step_def.agent_id},
                )

            try:
                output = await step_def.handler(ctx)
                step.status = MissionStepStatus.COMPLETED.value
                step.output_payload = output
                step.completed_at = datetime.now(UTC)
                if output:
                    results.update(output)

                await self._add_timeline(
                    ctx,
                    TimelineEventType.STEP_COMPLETED,
                    step_def.agent_id,
                    f"Step '{step_def.name}' completed",
                    {"step_id": step.id, "output": output},
                )
                if ctx.emit_event:
                    await ctx.emit_event(
                        "step_completed",
                        mission.id,
                        {"step": step_def.name, "output": output},
                    )
            except Exception as exc:
                step.status = MissionStepStatus.FAILED.value
                step.completed_at = datetime.now(UTC)
                mission.status = MissionStatus.FAILED.value
                mission.error_message = str(exc)
                mission.completed_at = datetime.now(UTC)

                await self._add_timeline(
                    ctx,
                    TimelineEventType.STEP_FAILED,
                    step_def.agent_id,
                    f"Step '{step_def.name}' failed: {exc}",
                    {"step_id": step.id},
                )
                if ctx.emit_event:
                    await ctx.emit_event(
                        "step_failed",
                        mission.id,
                        {"step": step_def.name, "error": str(exc)},
                    )
                raise

        mission.status = MissionStatus.COMPLETED.value
        mission.result_payload = results
        mission.completed_at = datetime.now(UTC)

        await self._add_timeline(
            ctx,
            TimelineEventType.MISSION_COMPLETED,
            "nova",
            f"Mission '{mission.title}' completed",
            {"result": results},
        )
        if ctx.emit_event:
            await ctx.emit_event("mission_completed", mission.id, {"result": results})

        return results

    async def _add_timeline(
        self,
        ctx: WorkflowContext,
        event_type: TimelineEventType,
        agent_id: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> TimelineEvent:
        event = TimelineEvent(
            mission_id=ctx.mission.id,
            event_type=event_type.value,
            agent_id=agent_id,
            message=message,
            payload=payload,
        )
        ctx.session.add(event)
        await ctx.session.flush()
        return event

    async def add_agent_message(
        self,
        ctx: WorkflowContext,
        agent_id: str,
        content: str,
        role: str = "assistant",
        evidence_badge: str = "verified",
    ) -> AgentMessage:
        msg = AgentMessage(
            mission_id=ctx.mission.id,
            agent_id=agent_id,
            role=role,
            content=content,
            evidence_badge=evidence_badge,
        )
        ctx.session.add(msg)
        await ctx.session.flush()
        return msg
