"""Phase 3B runtime services."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.auth.principal import Principal
from nova_core.automation.base import AutomationProviderKind
from nova_core.automation.runtime import AutomationRequest, AutomationRuntime
from nova_core.models.enums import ApprovalStatus
from nova_core.models.orm import (
    Approval,
    AutomationRun,
    ChatMessageRecord,
    ChatSession,
    ModelUsage,
    ScheduledTask,
)
from nova_core.providers.runtime import InferenceResult
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
from nova_core.utils.time import utc_now


class ChatSessionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        principal: Principal,
        session_id: str | None,
        *,
        title: str = "NOVA Chat",
    ) -> ChatSession:
        if session_id:
            result = await self.session.execute(
                select(ChatSession).where(
                    ChatSession.id == session_id,
                    ChatSession.user_id == principal.user_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing
            from nova_core.schemas.errors import NotFoundError

            raise NotFoundError("ChatSession", session_id)
        chat_session = ChatSession(
            user_id=principal.user_id,
            device_id=principal.device_id,
            title=title,
            provider_mode="auto_local_first",
            metadata_json={"source": "chat"},
        )
        self.session.add(chat_session)
        await self.session.flush()
        return chat_session

    async def append_message(
        self,
        chat_session: ChatSession,
        *,
        role: str,
        content: str,
        intent: str | None = None,
        blocked: bool = False,
        routing: dict[str, Any] | None = None,
        token_usage: dict[str, Any] | None = None,
    ) -> ChatMessageRecord:
        record = ChatMessageRecord(
            session_id=chat_session.id,
            role=role,
            content=content,
            intent=intent,
            blocked=blocked,
            routing=routing,
            token_usage=token_usage,
        )
        chat_session.updated_at = utc_now()
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_sessions(self, principal: Principal) -> list[ChatSession]:
        result = await self.session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == principal.user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(50)
        )
        return list(result.scalars().all())

    async def get_session(self, principal: Principal, session_id: str) -> ChatSession | None:
        result = await self.session.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == principal.user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_session(self, principal: Principal) -> ChatSession | None:
        result = await self.session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == principal.user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class RuntimeTelemetryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_model_usage(
        self,
        result: InferenceResult,
        *,
        agent_id: str | None = "nova",
        mission_id: str | None = None,
    ) -> None:
        self.session.add(
            ModelUsage(
                mission_id=mission_id,
                agent_id=agent_id,
                model_tier=result.mode,
                provider=result.provider.value,
                model_id=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=0.0 if not result.mode.startswith("paid_") else None,
            )
        )
        await self.session.flush()


class AutomationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.runtime = AutomationRuntime(settings)

    async def execute(
        self,
        principal: Principal,
        *,
        provider: str,
        action: str,
        payload: dict[str, Any],
        approval_id: str | None,
        dry_run: bool,
    ) -> AutomationRun:
        kind = AutomationProviderKind(provider)
        approved = await self._approval_is_granted(principal, approval_id)
        run = AutomationRun(
            user_id=principal.user_id,
            device_id=principal.device_id,
            provider=kind.value,
            action=action,
            status="running" if approved or dry_run else "blocked",
            requires_approval=not dry_run,
            approval_id=approval_id,
            request_payload=payload,
        )
        self.session.add(run)
        await self.session.flush()

        result = await self.runtime.execute(
            AutomationRequest(
                provider=kind,
                action=action,
                payload=payload,
                approved=approved,
                dry_run=dry_run,
            )
        )
        run.status = "completed" if result.success else "blocked"
        run.result_payload = (
            result.output if isinstance(result.output, dict) else {"output": result.output}
        )
        run.error_message = result.error
        run.requires_approval = result.requires_approval
        run.completed_at = utc_now()
        await record_audit_event(
            self.session,
            actor_type=principal.principal_type,
            actor_id=principal.principal_id,
            action="automation.execute",
            resource_type="automation_run",
            resource_id=run.id,
            details={
                "provider": kind.value,
                "automation_action": action,
                "status": run.status,
                "approved": approved,
                "dry_run": dry_run,
            },
        )
        await self.session.commit()
        return run

    async def schedule(
        self,
        principal: Principal,
        *,
        title: str,
        provider: str,
        action: str,
        schedule: str,
        payload: dict[str, Any],
    ) -> ScheduledTask:
        task = ScheduledTask(
            user_id=principal.user_id,
            device_id=principal.device_id,
            title=title,
            provider=AutomationProviderKind(provider).value,
            action=action,
            schedule=schedule,
            status="paused",
            payload=payload,
        )
        self.session.add(task)
        await record_audit_event(
            self.session,
            actor_type=principal.principal_type,
            actor_id=principal.principal_id,
            action="automation.schedule_created",
            resource_type="scheduled_task",
            resource_id=task.id,
            details={"provider": provider, "automation_action": action, "schedule": schedule},
        )
        await self.session.commit()
        return task

    async def list_scheduled(self, principal: Principal) -> list[ScheduledTask]:
        result = await self.session.execute(
            select(ScheduledTask)
            .where(ScheduledTask.user_id == principal.user_id)
            .order_by(ScheduledTask.created_at.desc())
            .limit(50)
        )
        return list(result.scalars().all())

    async def _approval_is_granted(self, principal: Principal, approval_id: str | None) -> bool:
        if not approval_id:
            return False
        result = await self.session.execute(select(Approval).where(Approval.id == approval_id))
        approval = result.scalar_one_or_none()
        if approval is None:
            return False
        return approval.status == ApprovalStatus.APPROVED.value
