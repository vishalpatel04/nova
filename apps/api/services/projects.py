"""Active project and project memory services."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.auth.principal import Principal
from nova_core.models.orm import ActiveProject, ProjectMemory
from nova_core.project.context import validate_project_root
from nova_core.project.inspect import _detect_tooling, inspect_repo
from nova_core.schemas.errors import NotFoundError, ValidationError
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        policies = settings.load_yaml("policies.yaml")
        safe_cfg = policies.get("safe_filesystem", {})
        self._allowed_roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None

    async def set_active_project(self, principal: Principal, project_root: str) -> ActiveProject:
        if not principal.device_id:
            raise ValidationError("Device id required to set active project")

        validation = validate_project_root(project_root, allowed_roots=self._allowed_roots)
        if not validation.allowed or validation.resolved is None:
            await record_audit_event(
                self.session,
                actor_type="device",
                actor_id=principal.device_id,
                action="project.set_blocked",
                resource_type="active_project",
                resource_id=None,
                details={"reason": validation.reason, "path": project_root[:200]},
            )
            raise ValidationError(validation.reason or "Blocked project root")

        root = validation.resolved
        tooling = _detect_tooling(root)
        branch: str | None = None
        try:
            inspection = await inspect_repo(root)
            raw_branch = inspection.current_branch or None
            branch = None if raw_branch == "" else raw_branch
        except Exception:
            pass

        result = await self.session.execute(
            select(ActiveProject).where(ActiveProject.device_id == principal.device_id)
        )
        record = result.scalar_one_or_none()
        now = _utc_now()
        if record is None:
            record = ActiveProject(
                user_id=principal.user_id,
                device_id=principal.device_id,
                project_root=str(root),
                project_name=root.name,
                current_branch=branch or None,
                detected_tooling=tooling,
                last_opened_at=now,
            )
            self.session.add(record)
        else:
            record.user_id = principal.user_id
            record.project_root = str(root)
            record.project_name = root.name
            record.current_branch = branch or None
            record.detected_tooling = tooling
            record.last_opened_at = now

        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id,
            action="project.set",
            resource_type="active_project",
            resource_id=record.id,
            details={"project_root": str(root), "project_name": root.name},
        )
        await self.session.flush()
        return record

    async def _clear_if_stale(self, record: ActiveProject) -> ActiveProject | None:
        path = Path(record.project_root)
        if path.exists() and path.is_dir():
            return record
        await record_audit_event(
            self.session,
            actor_type="system",
            actor_id="project_service",
            action="project.cleared_stale",
            resource_type="active_project",
            resource_id=record.id,
            details={"project_root": record.project_root[:200]},
        )
        await self.session.delete(record)
        await self.session.flush()
        return None

    async def get_active_project(self, principal: Principal) -> ActiveProject:
        if not principal.device_id:
            raise ValidationError("Device id required")
        result = await self.session.execute(
            select(ActiveProject).where(
                ActiveProject.device_id == principal.device_id,
                ActiveProject.user_id == principal.user_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundError("active_project", principal.device_id)
        fresh = await self._clear_if_stale(record)
        if fresh is None:
            raise NotFoundError("active_project", principal.device_id)
        return fresh

    async def get_active_project_or_none(self, principal: Principal) -> ActiveProject | None:
        if not principal.device_id:
            return None
        result = await self.session.execute(
            select(ActiveProject).where(
                ActiveProject.device_id == principal.device_id,
                ActiveProject.user_id == principal.user_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return await self._clear_if_stale(record)

    async def get_memory(self, principal: Principal, project_root: str) -> ProjectMemory | None:
        if not principal.device_id:
            return None
        result = await self.session.execute(
            select(ProjectMemory).where(
                ProjectMemory.user_id == principal.user_id,
                ProjectMemory.device_id == principal.device_id,
                ProjectMemory.project_root == project_root,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_memory(
        self,
        principal: Principal,
        project_root: str,
        **fields: Any,
    ) -> ProjectMemory:
        if not principal.device_id:
            raise ValidationError("Device id required")
        record = await self.get_memory(principal, project_root)
        if record is None:
            record = ProjectMemory(
                user_id=principal.user_id,
                device_id=principal.device_id,
                project_root=project_root,
            )
            self.session.add(record)
        for key, value in fields.items():
            if hasattr(record, key):
                setattr(record, key, value)
        await self.session.flush()
        return record

    async def append_task_history(
        self,
        principal: Principal,
        project_root: str,
        entry: dict[str, Any],
        *,
        max_entries: int = 10,
    ) -> None:
        memory = await self.upsert_memory(principal, project_root)
        history = list(memory.recent_task_history or [])
        history.insert(0, entry)
        memory.recent_task_history = history[:max_entries]
