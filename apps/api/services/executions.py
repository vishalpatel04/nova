"""Run approved shell commands with strict safety gates."""

from __future__ import annotations

from datetime import datetime
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
from nova_core.models.orm import ApprovalRequest, ShellExecution
from nova_core.schemas.errors import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
from nova_core.shell.executor import execute_safe_command
from nova_core.shell.safe_command import validate_safe_shell_command


class ControlledExecutionService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._policies = settings.load_yaml("policies.yaml")
        safe_cfg = self._policies.get("safe_filesystem", {})
        self._allowed_roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None
        self._approval_svc = ApprovalRequestService(session, settings)

    async def run_approved(self, principal: Principal, approval_id: str) -> ShellExecution:
        if not principal.device_id:
            raise ValidationError("Device id required for execution")

        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id,
            action="execution.requested",
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
        if record.capability != CapabilityName.SHELL_EXECUTE.value:
            raise ValidationError("Approval is not for shell execution")
        if record.status == ActionApprovalStatus.PENDING.value:
            raise ConflictError("Approval is still pending")
        if record.status == ActionApprovalStatus.REJECTED.value:
            raise ConflictError("Approval was rejected")
        if record.status == ActionApprovalStatus.EXPIRED.value:
            raise ConflictError("Approval expired")
        if record.status == ActionApprovalStatus.CONSUMED.value:
            raise ConflictError("Approval already consumed")
        if record.status != ActionApprovalStatus.APPROVED.value:
            raise ConflictError(f"Approval status {record.status} cannot execute")
        if _as_utc(record.expires_at) < _utc_now():
            raise ConflictError("Approval expired")

        payload = (record.metadata_json or {}).get("payload") or {}
        command = str(payload.get("command", "")).strip()
        if not command:
            raise ValidationError("Approval payload missing command")

        validation = validate_safe_shell_command(command, allowed_roots=self._allowed_roots)
        if not validation.allowed:
            execution = await self._record_execution(
                principal,
                record,
                status=ExecutionStatus.BLOCKED,
                command_preview=command,
                fingerprint=record.action_fingerprint,
                stderr=validation.reason or "Command blocked",
                exit_code=-1,
                audit_action="execution.blocked",
            )
            return execution

        fingerprint = compute_action_fingerprint(
            CapabilityName.SHELL_EXECUTE.value,
            {"command": command},
        )
        if fingerprint != record.action_fingerprint:
            raise ConflictError("Approval action fingerprint mismatch")

        await self._approval_svc.consume(
            principal,
            approval_id,
            expected_fingerprint=fingerprint,
        )

        existing = await self.session.execute(
            select(ShellExecution.id).where(ShellExecution.approval_id == approval_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("Approval already executed")

        execution = await self._record_execution(
            principal,
            record,
            status=ExecutionStatus.RUNNING,
            command_preview=command,
            fingerprint=fingerprint,
            audit_action="execution.started",
            started_at=_utc_now(),
        )

        result = await execute_safe_command(validation)
        if result.blocked:
            execution.status = ExecutionStatus.BLOCKED.value
            execution.stderr_excerpt = result.block_reason
            execution.exit_code = -1
            audit_action = "execution.blocked"
        elif result.timed_out:
            execution.status = ExecutionStatus.TIMED_OUT.value
            execution.stderr_excerpt = result.stderr_excerpt
            execution.exit_code = -1
            audit_action = "execution.timed_out"
        elif result.exit_code == 0:
            execution.status = ExecutionStatus.SUCCEEDED.value
            execution.stdout_excerpt = result.stdout_excerpt
            execution.stderr_excerpt = result.stderr_excerpt or None
            execution.exit_code = result.exit_code
            audit_action = "execution.succeeded"
        else:
            execution.status = ExecutionStatus.FAILED.value
            execution.stdout_excerpt = result.stdout_excerpt or None
            execution.stderr_excerpt = result.stderr_excerpt or None
            execution.exit_code = result.exit_code
            audit_action = "execution.failed"

        execution.finished_at = _utc_now()
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id,
            action=audit_action,
            resource_type="shell_execution",
            resource_id=execution.id,
            details={
                "approval_id": approval_id,
                "exit_code": execution.exit_code,
                "status": execution.status,
            },
        )
        await self.session.flush()
        return execution

    async def _record_execution(
        self,
        principal: Principal,
        record: Any,
        *,
        status: ExecutionStatus,
        command_preview: str,
        fingerprint: str,
        audit_action: str,
        started_at: datetime | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
    ) -> ShellExecution:
        execution = ShellExecution(
            approval_id=record.id,
            user_id=principal.user_id,
            device_id=principal.device_id or record.device_id,
            capability=record.capability,
            action_fingerprint=fingerprint,
            command_preview=command_preview[:4000],
            status=status.value,
            stdout_excerpt=stdout,
            stderr_excerpt=stderr,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=None if status == ExecutionStatus.RUNNING else started_at,
            metadata_json={"command": command_preview[:500]},
        )
        self.session.add(execution)
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action=audit_action,
            resource_type="shell_execution",
            resource_id=execution.id,
            details={"approval_id": record.id, "status": status.value},
        )
        await self.session.flush()
        return execution
