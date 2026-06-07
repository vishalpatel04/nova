"""Agent plan orchestration — create, run, approve, retry, cancel."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.approvals import ApprovalRequestService
from apps.api.services.patch_executions import PatchExecutionService
from apps.api.services.projects import ProjectService
from nova_core.auth.principal import Principal
from nova_core.capabilities.model import CapabilityName, risk_for_capability
from nova_core.models.enums import (
    AgentPlanStatus,
    AgentPlanStepStatus,
)
from nova_core.models.orm import AgentPlan, AgentPlanStep, ProjectDecision
from nova_core.orchestration.executor import OrchestrationExecutor
from nova_core.orchestration.step_types import (
    DEFAULT_MAX_STEPS,
    MAX_RETRIES_PER_STEP,
    build_default_repair_plan,
    validate_step_action,
)
from nova_core.patch.policy import build_patch_preview
from nova_core.project.context import validate_project_root
from nova_core.providers.trust_lanes import active_lane, trust_lane_summary
from nova_core.schemas.errors import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AgentPlanService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        policies = settings.load_yaml("policies.yaml")
        safe_cfg = policies.get("safe_filesystem", {})
        self._allowed_roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None
        self._project_svc = ProjectService(session, settings)
        self._approval_svc = ApprovalRequestService(session, settings)
        self._patch_svc = PatchExecutionService(session, settings)

    async def create_plan(
        self,
        principal: Principal,
        *,
        objective: str,
        title: str | None = None,
        draft: bool = False,
        project_root: str | None = None,
    ) -> AgentPlan:
        if not principal.device_id:
            raise ValidationError("Device id required for agent plans")
        if project_root:
            root_validation = validate_project_root(project_root, allowed_roots=self._allowed_roots)
            if not root_validation.allowed:
                raise ValidationError(root_validation.reason or "Project root blocked")
            resolved_root = str(root_validation.resolved)
        else:
            active = await self._project_svc.get_active_project(principal)
            resolved_root = active.project_root

        lane = active_lane(self.settings)
        step_specs = build_default_repair_plan(objective=objective)
        if len(step_specs) > DEFAULT_MAX_STEPS:
            raise ValidationError(f"Plan exceeds max {DEFAULT_MAX_STEPS} steps")

        plan = AgentPlan(
            user_id=principal.user_id,
            device_id=principal.device_id,
            project_root=resolved_root,
            title=title or f"Repair: {objective[:80]}",
            objective=objective,
            status=AgentPlanStatus.DRAFT.value if draft else AgentPlanStatus.RUNNING.value,
            provider_lane=lane.value,
            max_steps=DEFAULT_MAX_STEPS,
            current_step_index=0,
            metadata_json={"running": False},
        )
        self.session.add(plan)
        await self.session.flush()

        for spec in step_specs:
            ok, reason = validate_step_action(spec["action_type"])
            if not ok:
                raise ValidationError(reason or "Invalid step")
            step = AgentPlanStep(
                plan_id=plan.id,
                step_index=spec["step_index"],
                agent_role=spec["agent_role"],
                action_type=spec["action_type"],
                status=AgentPlanStepStatus.PENDING.value,
                input_summary=spec.get("input_summary"),
            )
            self.session.add(step)
        await self.session.flush()
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id,
            action="agent_plan.created",
            resource_type="agent_plan",
            resource_id=plan.id,
            details={"steps": len(step_specs), "draft": draft},
        )
        if not draft:
            await self.run_plan(principal, plan.id)
        return plan

    async def create_draft_from_validation_failure(
        self,
        *,
        user_id: str,
        device_id: str,
        project_root: str,
        objective: str,
        source_task_id: str | None = None,
    ) -> AgentPlan:
        """Background hook — draft plan only, never auto-run patch/commit."""
        principal = Principal(
            principal_type="device",
            principal_id=device_id,
            user_id=user_id,
            device_id=device_id,
        )
        plan = await self.create_plan(
            principal,
            objective=objective,
            title="Draft repair plan (validation failed)",
            draft=True,
            project_root=project_root,
        )
        meta = dict(plan.metadata_json or {})
        meta["source_task_id"] = source_task_id
        meta["background_draft"] = True
        plan.metadata_json = meta
        await self.session.flush()
        return plan

    async def get_plan(self, principal: Principal, plan_id: str) -> AgentPlan | None:
        plan = await self.session.get(AgentPlan, plan_id)
        if plan is None:
            return None
        if plan.user_id != principal.user_id or plan.device_id != principal.device_id:
            raise UnauthorizedError("Agent plan ownership mismatch")
        return plan

    async def get_active_plan(self, principal: Principal) -> AgentPlan | None:
        if not principal.device_id:
            return None
        result = await self.session.execute(
            select(AgentPlan)
            .where(
                AgentPlan.user_id == principal.user_id,
                AgentPlan.device_id == principal.device_id,
                AgentPlan.status.in_(
                    [
                        AgentPlanStatus.DRAFT.value,
                        AgentPlanStatus.RUNNING.value,
                        AgentPlanStatus.WAITING_APPROVAL.value,
                    ]
                ),
            )
            .order_by(AgentPlan.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_plans(self, principal: Principal, *, limit: int = 20) -> list[AgentPlan]:
        if not principal.device_id:
            return []
        result = await self.session.execute(
            select(AgentPlan)
            .where(
                AgentPlan.user_id == principal.user_id,
                AgentPlan.device_id == principal.device_id,
            )
            .order_by(AgentPlan.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def cancel_plan(self, principal: Principal, plan_id: str) -> AgentPlan:
        plan = await self._get_owned_plan(plan_id, principal)
        if plan.status in {AgentPlanStatus.COMPLETED.value, AgentPlanStatus.CANCELLED.value}:
            raise ConflictError(f"Plan already {plan.status}")
        plan.status = AgentPlanStatus.CANCELLED.value
        plan.updated_at = _utc_now()
        await self._set_running_flag(plan, False)
        await self.session.flush()
        return plan

    async def run_plan(self, principal: Principal, plan_id: str) -> dict[str, Any]:
        plan = await self._get_owned_plan(plan_id, principal)
        meta = dict(plan.metadata_json or {})
        if meta.get("running"):
            raise ConflictError("Plan already has an active run")
        meta["running"] = True
        plan.metadata_json = meta
        plan.status = AgentPlanStatus.RUNNING.value
        await self.session.flush()

        executor = OrchestrationExecutor(self.settings, allowed_roots=self._allowed_roots)
        context = dict(meta.get("context") or {})
        executor.set_context(context)
        project_root = Path(plan.project_root)

        steps = await self._load_steps(plan.id)
        start_index = plan.current_step_index or 0

        for step in steps:
            if step.step_index < start_index:
                continue
            if step.status == AgentPlanStepStatus.COMPLETED.value:
                continue
            if step.status == AgentPlanStepStatus.WAITING_APPROVAL.value:
                plan.status = AgentPlanStatus.WAITING_APPROVAL.value
                await self._set_running_flag(plan, False)
                await self.session.flush()
                return self._plan_response(plan, steps, paused=True)

            step.status = AgentPlanStepStatus.RUNNING.value
            step.started_at = _utc_now()
            plan.current_step_index = step.step_index
            await self.session.flush()

            result = await executor.execute(
                action_type=step.action_type,
                agent_role=step.agent_role,
                project_root=project_root,
                objective=plan.objective,
                step_input=step.input_summary,
            )

            step.output_summary = result.output_summary[:4000]
            step.evidence_json = self._bounded_evidence(result.evidence)
            step.finished_at = _utc_now()

            if result.waiting_approval or result.status_override == "waiting_approval":
                step.status = AgentPlanStepStatus.WAITING_APPROVAL.value
                plan.status = AgentPlanStatus.WAITING_APPROVAL.value
                context = executor._context
                if context.get("patch_payload") and not context.get("approval_id"):
                    approval = await self._create_patch_approval(principal, plan, context)
                    context["approval_id"] = approval.id
                    step.evidence_json = {
                        **(step.evidence_json or {}),
                        "approval_id": approval.id,
                    }
                meta["context"] = context
                plan.metadata_json = meta
                await self._set_running_flag(plan, False)
                await self.session.flush()
                return self._plan_response(plan, steps, waiting_approval=True)

            if result.blocked or result.status_override == "blocked":
                step.status = AgentPlanStepStatus.BLOCKED.value
                plan.status = AgentPlanStatus.FAILED.value
                await self._set_running_flag(plan, False)
                await self.session.flush()
                return self._plan_response(plan, steps, failed=True)

            if not result.success:
                if step.retry_count < MAX_RETRIES_PER_STEP:
                    step.retry_count += 1
                    step.status = AgentPlanStepStatus.PENDING.value
                    step.started_at = None
                    step.finished_at = None
                    await self.session.flush()
                    continue
                step.status = AgentPlanStepStatus.FAILED.value
                plan.status = AgentPlanStatus.FAILED.value
                await self._set_running_flag(plan, False)
                await self.session.flush()
                return self._plan_response(plan, steps, failed=True)

            step.status = AgentPlanStepStatus.COMPLETED.value

        meta["context"] = executor._context
        plan.metadata_json = meta
        plan.status = AgentPlanStatus.COMPLETED.value
        plan.summary = (executor._context.get("final_report") or "Plan completed")[:8000]
        await self._set_running_flag(plan, False)
        await self._record_decision(principal, plan, executor._context)
        await self.session.flush()
        return self._plan_response(plan, steps, completed=True)

    async def retry_step(
        self, principal: Principal, plan_id: str, step_index: int
    ) -> dict[str, Any]:
        plan = await self._get_owned_plan(plan_id, principal)
        steps = await self._load_steps(plan.id)
        step = next((s for s in steps if s.step_index == step_index), None)
        if step is None:
            raise NotFoundError("agent_plan_step", str(step_index))
        if step.status not in {
            AgentPlanStepStatus.FAILED.value,
            AgentPlanStepStatus.BLOCKED.value,
        }:
            raise ConflictError(f"Step {step_index} is not retryable (status={step.status})")
        step.status = AgentPlanStepStatus.PENDING.value
        step.retry_count = 0
        plan.current_step_index = step_index
        plan.status = AgentPlanStatus.RUNNING.value
        await self.session.flush()
        return await self.run_plan(principal, plan_id)

    async def mark_patch_applied(
        self, principal: Principal, plan_id: str, *, applied_files: list[str]
    ) -> AgentPlan:
        plan = await self._get_owned_plan(plan_id, principal)
        meta = dict(plan.metadata_json or {})
        context = dict(meta.get("context") or {})
        context["patch_applied"] = True
        context["applied_files"] = applied_files
        meta["context"] = context
        plan.metadata_json = meta
        plan.status = AgentPlanStatus.RUNNING.value
        await self._set_running_flag(plan, False)
        await self.session.flush()
        return plan

    async def continue_after_patch_apply(
        self, principal: Principal, plan_id: str
    ) -> dict[str, Any]:
        plan = await self.mark_patch_applied(principal, plan_id, applied_files=[])
        steps = await self._load_steps(plan.id)
        waiting = AgentPlanStepStatus.WAITING_APPROVAL.value
        completed = AgentPlanStepStatus.COMPLETED.value
        for step in steps:
            if step.action_type == "patch.await_approval" and step.status == waiting:
                step.status = completed
            if step.action_type == "patch.apply_approved" and step.status != completed:
                step.status = completed
                step.output_summary = "Patch applied by user"
        plan.current_step_index = (
            max(
                (s.step_index for s in steps if s.status == AgentPlanStepStatus.COMPLETED.value),
                default=0,
            )
            + 1
        )
        await self.session.flush()
        return await self.run_plan(principal, plan_id)

    def provider_lane_info(self) -> dict[str, Any]:
        return trust_lane_summary(self.settings)

    async def _create_patch_approval(
        self, principal: Principal, plan: AgentPlan, context: dict[str, Any]
    ) -> Any:
        payload = context.get("patch_payload") or {}
        preview = build_patch_preview(payload)
        return await self._approval_svc.create_request(
            principal,
            capability=CapabilityName.CODE_PATCH,
            action_summary=f"Orchestration patch: {plan.title[:100]}",
            preview=preview,
            payload=payload,
            risk_level=risk_for_capability(CapabilityName.CODE_PATCH),
        )

    async def _get_owned_plan(self, plan_id: str, principal: Principal) -> AgentPlan:
        plan = await self.session.get(AgentPlan, plan_id)
        if plan is None:
            raise NotFoundError("agent_plan", plan_id)
        if plan.user_id != principal.user_id or plan.device_id != principal.device_id:
            raise UnauthorizedError("Agent plan ownership mismatch")
        return plan

    async def _load_steps(self, plan_id: str) -> list[AgentPlanStep]:
        result = await self.session.execute(
            select(AgentPlanStep)
            .where(AgentPlanStep.plan_id == plan_id)
            .order_by(AgentPlanStep.step_index.asc())
        )
        return list(result.scalars().all())

    async def _set_running_flag(self, plan: AgentPlan, running: bool) -> None:
        meta = dict(plan.metadata_json or {})
        meta["running"] = running
        plan.metadata_json = meta
        plan.updated_at = _utc_now()

    async def _record_decision(
        self, principal: Principal, plan: AgentPlan, context: dict[str, Any]
    ) -> None:
        decision = ProjectDecision(
            user_id=principal.user_id,
            project_root=plan.project_root,
            title=f"Plan outcome: {plan.title[:100]}",
            summary=(plan.summary or plan.objective)[:4000],
            source_plan_id=plan.id,
            metadata_json={
                "reviewer_verdict": context.get("reviewer_verdict"),
                "validation": context.get("rerun_validation") or context.get("validation"),
                "commit_proposal": context.get("commit_proposal"),
            },
        )
        self.session.add(decision)

    @staticmethod
    def _bounded_evidence(evidence: dict[str, Any] | None) -> dict[str, Any] | None:
        if not evidence:
            return None
        bounded: dict[str, Any] = {}
        for key, value in evidence.items():
            if key == "patch_payload":
                if isinstance(value, dict):
                    summary_text = str(value.get("summary", ""))[:500]
                    file_count = len(value.get("files", []))
                else:
                    summary_text = str(value)[:500]
                    file_count = 0
                bounded[key] = {
                    "summary": summary_text,
                    "file_count": file_count,
                }
            elif isinstance(value, str):
                bounded[key] = value[:2000]
            else:
                bounded[key] = value
        return bounded

    @staticmethod
    def _plan_response(
        plan: AgentPlan,
        steps: list[AgentPlanStep],
        *,
        completed: bool = False,
        failed: bool = False,
        waiting_approval: bool = False,
        paused: bool = False,
    ) -> dict[str, Any]:
        meta = plan.metadata_json or {}
        context = meta.get("context") or {}
        return {
            "plan_id": plan.id,
            "status": plan.status,
            "title": plan.title,
            "objective": plan.objective,
            "provider_lane": plan.provider_lane,
            "current_step_index": plan.current_step_index,
            "summary": plan.summary,
            "completed": completed,
            "failed": failed,
            "waiting_approval": waiting_approval or paused,
            "approval_id": context.get("approval_id"),
            "patch_preview": context.get("patch_preview", "")[:2000] if context else None,
            "reviewer_verdict": context.get("reviewer_verdict"),
            "commit_proposal": context.get("commit_proposal"),
            "steps": [
                {
                    "step_index": s.step_index,
                    "agent_role": s.agent_role,
                    "action_type": s.action_type,
                    "status": s.status,
                    "input_summary": s.input_summary,
                    "output_summary": (s.output_summary or "")[:1000],
                    "retry_count": s.retry_count,
                }
                for s in steps
            ],
        }

    def plan_to_dict(
        self, plan: AgentPlan, steps: list[AgentPlanStep] | None = None
    ) -> dict[str, Any]:
        return self._plan_response(plan, steps or [])
