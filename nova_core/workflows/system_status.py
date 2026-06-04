"""System status mission workflow — NOVA queries worker heartbeats and reports."""

from typing import Any

from nova_core.devices.availability import get_worker_availability
from nova_core.models.enums import TimelineEventType
from nova_core.workflows.base import BaseWorkflow, WorkflowContext, WorkflowStepDefinition


class SystemStatusWorkflow(BaseWorkflow):
    mission_type = "system_status"

    def steps(self) -> list[WorkflowStepDefinition]:
        return [
            WorkflowStepDefinition(
                name="query_worker_heartbeats",
                agent_id="nova",
                handler=self._query_workers,
            ),
            WorkflowStepDefinition(
                name="calculate_availability",
                agent_id="nova",
                handler=self._calculate_availability,
            ),
            WorkflowStepDefinition(
                name="generate_summary",
                agent_id="nova",
                handler=self._generate_summary,
            ),
        ]

    async def _query_workers(self, ctx: WorkflowContext) -> dict[str, Any]:
        availability = await get_worker_availability(ctx.session, ctx.settings)
        ctx.extra["availability"] = availability

        await self._add_timeline(
            ctx,
            TimelineEventType.WORKER_HEARTBEAT,
            "nova",
            f"Queried {availability['workers_total']} registered workers",
            availability,
        )

        await self.add_agent_message(
            ctx,
            "nova",
            f"Found {availability['workers_total']} registered worker(s): "
            f"{availability['workers_online']} online, "
            f"{availability['workers_stale']} stale, "
            f"{availability['workers_offline']} offline.",
            evidence_badge="verified",
        )
        return {"availability": availability}

    async def _calculate_availability(self, ctx: WorkflowContext) -> dict[str, Any]:
        availability = ctx.extra.get("availability", {})
        total = availability.get("workers_total", 0)
        online = availability.get("workers_online", 0)

        if total == 0:
            health = "no_workers_registered"
            message = "No worker nodes are registered. Deploy a worker daemon to enable execution."
        elif online == 0:
            health = "all_workers_offline"
            message = "All registered workers are offline or stale."
        elif online < total:
            health = "degraded"
            message = f"{online}/{total} workers online — system is degraded."
        else:
            health = "healthy"
            message = f"All {total} worker(s) are online."

        ctx.extra["health"] = health
        ctx.extra["health_message"] = message

        await self._add_timeline(
            ctx,
            TimelineEventType.SYSTEM_STATUS,
            "nova",
            message,
            {"health": health, "online": online, "total": total},
        )
        return {"health": health, "health_message": message}

    async def _generate_summary(self, ctx: WorkflowContext) -> dict[str, Any]:
        availability = ctx.extra.get("availability", {})
        health = ctx.extra.get("health", "unknown")
        health_message = ctx.extra.get("health_message", "")

        summary = {
            "health": health,
            "message": health_message,
            "workers": availability,
            "control_plane": "operational",
        }

        await self.add_agent_message(
            ctx,
            "nova",
            f"System status: {health_message}",
            evidence_badge="verified",
        )

        if ctx.emit_event:
            await ctx.emit_event("system_status", ctx.mission.id, summary)

        return {"summary": summary}


WORKFLOW_REGISTRY: dict[str, type[BaseWorkflow]] = {
    "system_status": SystemStatusWorkflow,
}
