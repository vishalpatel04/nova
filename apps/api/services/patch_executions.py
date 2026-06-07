"""Apply approved code patches with strict safety gates."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.approvals import ApprovalRequestService, _as_utc, _utc_now
from nova_core.auth.principal import Principal
from nova_core.capabilities.model import (
    ActionApprovalStatus,
    CapabilityName,
    compute_action_fingerprint,
)
from nova_core.models.enums import ExecutionStatus
from nova_core.models.orm import ApprovalRequest, PatchExecution
from nova_core.patch.apply import apply_patch_payload
from nova_core.patch.policy import build_patch_preview, validate_patch_payload
from nova_core.project.context import validate_project_root
from nova_core.schemas.errors import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event

PATCH_CAPABILITIES = frozenset({CapabilityName.CODE_PATCH.value, CapabilityName.FILE_WRITE.value})


class PatchExecutionService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        policies = settings.load_yaml("policies.yaml")
        safe_cfg = policies.get("safe_filesystem", {})
        self._allowed_roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None
        self._approval_svc = ApprovalRequestService(session, settings)

    async def apply_approved_patch(self, principal: Principal, approval_id: str) -> PatchExecution:
        if not principal.device_id:
            raise ValidationError("Device id required for patch application")

        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id,
            action="patch.requested",
            resource_type="approval_request",
            resource_id=approval_id,
            details={},
        )

        locked = await self.session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == approval_id).with_for_update()
        )
        record = locked.scalar_one_or_none()
        if record is None:
            raise NotFoundError("approval_request", approval_id)
        if record.user_id != principal.user_id or record.device_id != principal.device_id:
            raise UnauthorizedError("Approval request ownership mismatch")
        if record.capability not in PATCH_CAPABILITIES:
            raise ValidationError("Approval is not for patch or file write")
        if record.status == ActionApprovalStatus.PENDING.value:
            raise ConflictError("Approval is still pending")
        if record.status == ActionApprovalStatus.REJECTED.value:
            raise ConflictError("Approval was rejected")
        if record.status == ActionApprovalStatus.EXPIRED.value:
            raise ConflictError("Approval expired")
        if record.status == ActionApprovalStatus.CONSUMED.value:
            raise ConflictError("Approval already consumed")
        if record.status != ActionApprovalStatus.APPROVED.value:
            raise ConflictError(f"Approval status {record.status} cannot apply patch")
        if _as_utc(record.expires_at) < _utc_now():
            raise ConflictError("Approval expired")

        payload = (record.metadata_json or {}).get("payload") or {}
        project_root_raw = str(payload.get("project_root", "")).strip()
        if not project_root_raw:
            raise ValidationError("Approval payload missing project_root")

        root_validation = validate_project_root(project_root_raw, allowed_roots=self._allowed_roots)
        if not root_validation.allowed or root_validation.resolved is None:
            execution = await self._record_execution(
                principal,
                record,
                project_root=project_root_raw,
                status=ExecutionStatus.BLOCKED,
                preview=build_patch_preview(payload),
                fingerprint=record.action_fingerprint,
                error=root_validation.reason or "Project root blocked",
                audit_action="patch.blocked",
            )
            return execution

        project_root = root_validation.resolved
        patch_validation = validate_patch_payload(project_root, payload)
        if not patch_validation.allowed:
            execution = await self._record_execution(
                principal,
                record,
                project_root=str(project_root),
                status=ExecutionStatus.BLOCKED,
                preview=build_patch_preview(payload),
                fingerprint=record.action_fingerprint,
                error=patch_validation.reason or "Patch blocked",
                audit_action="patch.blocked",
            )
            return execution

        fingerprint = compute_action_fingerprint(record.capability, payload)
        if fingerprint != record.action_fingerprint:
            raise ConflictError("Approval action fingerprint mismatch")

        await self._approval_svc.consume(
            principal,
            approval_id,
            expected_fingerprint=fingerprint,
        )

        existing = await self.session.execute(
            select(PatchExecution.id).where(PatchExecution.approval_id == approval_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("Approval already applied")

        preview = build_patch_preview(payload)
        execution = await self._record_execution(
            principal,
            record,
            project_root=str(project_root),
            status=ExecutionStatus.RUNNING,
            preview=preview,
            fingerprint=fingerprint,
            audit_action="patch.started",
            started_at=_utc_now(),
        )

        apply_result = apply_patch_payload(project_root, patch_validation)
        if apply_result.success:
            execution.status = ExecutionStatus.SUCCEEDED.value
            execution.applied_files = list(apply_result.applied_files)
            audit_action = "patch.applied"
        else:
            execution.status = ExecutionStatus.FAILED.value
            execution.error_message = apply_result.error
            audit_action = "patch.failed"

        execution.finished_at = _utc_now()
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id,
            action=audit_action,
            resource_type="patch_execution",
            resource_id=execution.id,
            details={
                "approval_id": approval_id,
                "status": execution.status,
                "files": execution.applied_files or [],
            },
        )
        await self.session.flush()
        return execution

    async def _record_execution(
        self,
        principal: Principal,
        record: ApprovalRequest,
        *,
        project_root: str,
        status: ExecutionStatus,
        preview: str,
        fingerprint: str,
        audit_action: str,
        started_at: datetime | None = None,
        error: str | None = None,
        applied_files: list[str] | None = None,
    ) -> PatchExecution:
        execution = PatchExecution(
            approval_id=record.id,
            user_id=principal.user_id,
            device_id=principal.device_id or record.device_id,
            capability=record.capability,
            action_fingerprint=fingerprint,
            project_root=project_root,
            patch_preview=preview[:8000],
            status=status.value,
            applied_files=applied_files,
            error_message=error,
            started_at=started_at,
            finished_at=None if status == ExecutionStatus.RUNNING else started_at,
            metadata_json={"capability": record.capability},
        )
        self.session.add(execution)
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action=audit_action,
            resource_type="patch_execution",
            resource_id=execution.id,
            details={"approval_id": record.id, "status": status.value},
        )
        await self.session.flush()
        return execution

    @staticmethod
    def revalidate_patch_on_worker(
        project_root: Path,
        payload: dict[str, Any],
        *,
        allowed_roots: list[str] | None = None,
    ) -> tuple[bool, str | None]:
        """Worker-side policy revalidation before apply."""
        root_check = validate_project_root(str(project_root), allowed_roots=allowed_roots)
        if not root_check.allowed:
            return False, root_check.reason
        validation = validate_patch_payload(project_root, payload)
        if not validation.allowed:
            return False, validation.reason
        return True, None
