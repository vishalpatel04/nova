"""Safe execution of predefined background task types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.background.task_types import (
    PROJECT_SCOPED_TASK_TYPES,
    REMINDER_TASK_TYPES,
    SYSTEM_SCOPED_TASK_TYPES,
)
from nova_core.devices.availability import get_worker_availability
from nova_core.models.enums import BackgroundTaskType
from nova_core.project.context import validate_project_root
from nova_core.project.inspect import format_inspection, inspect_repo
from nova_core.project.validation import pick_validation_command, run_validation_command
from nova_core.schemas.settings import Settings


@dataclass(frozen=True)
class BackgroundTaskExecutionResult:
    success: bool
    summary: str
    error: str | None = None
    evidence: dict[str, Any] | None = None
    validation_exit_code: int | None = None


class BackgroundTaskExecutor:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        policies = settings.load_yaml("policies.yaml")
        safe_cfg = policies.get("safe_filesystem", {})
        self._allowed_roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None

    async def execute(
        self,
        *,
        task_type: str,
        project_root: str | None,
        prompt: str | None,
    ) -> BackgroundTaskExecutionResult:
        if task_type in PROJECT_SCOPED_TASK_TYPES:
            if not project_root:
                return BackgroundTaskExecutionResult(
                    success=False,
                    summary="Missing project_root",
                    error="project_root required",
                )
            validation = validate_project_root(project_root, allowed_roots=self._allowed_roots)
            if not validation.allowed or validation.resolved is None:
                return BackgroundTaskExecutionResult(
                    success=False,
                    summary="Blocked project root",
                    error=validation.reason,
                )
            root = validation.resolved
            if task_type == BackgroundTaskType.REPO_INSPECT.value:
                inspection = await inspect_repo(root)
                text = format_inspection(inspection)
                return BackgroundTaskExecutionResult(
                    success=True,
                    summary=f"Inspected {inspection.project_name}",
                    evidence={"inspection_excerpt": text[:1500]},
                )
            if task_type == BackgroundTaskType.PROJECT_SUMMARY.value:
                inspection = await inspect_repo(root)
                summary = (
                    f"{inspection.project_name} @ {inspection.current_branch or '(no git)'}\n"
                    f"Validation: {inspection.detected_commands.get('test', 'none')}"
                )
                return BackgroundTaskExecutionResult(
                    success=True,
                    summary=summary[:500],
                    evidence={"branch": inspection.current_branch},
                )
            if task_type in {
                BackgroundTaskType.REPO_RUN_VALIDATION.value,
                BackgroundTaskType.REPO_HEALTH_CHECK.value,
            }:
                cmd = pick_validation_command(root) or "make test"
                result = await run_validation_command(root, cmd, allowed_roots=self._allowed_roots)
                success = result.exit_code == 0 and not result.blocked
                summary = (
                    f"Validation {cmd}: exit {result.exit_code}"
                    if success
                    else f"Validation failed ({cmd}): exit {result.exit_code}"
                )
                evidence = {
                    "command": cmd,
                    "exit_code": result.exit_code,
                    "stdout_excerpt": result.stdout_excerpt[:1500],
                    "stderr_excerpt": result.stderr_excerpt[:1500],
                    "blocked": result.blocked,
                }
                return BackgroundTaskExecutionResult(
                    success=success,
                    summary=summary,
                    error=None if success else (result.block_reason or "validation failed"),
                    evidence=evidence,
                    validation_exit_code=result.exit_code,
                )

        if task_type in SYSTEM_SCOPED_TASK_TYPES:
            availability = await get_worker_availability(self.session, self.settings)
            summary = (
                f"Workers online {availability['workers_online']}/"
                f"{availability['workers_total']} "
                f"(stale {availability['workers_stale']})"
            )
            return BackgroundTaskExecutionResult(
                success=True,
                summary=summary,
                evidence={
                    "workers_online": availability["workers_online"],
                    "workers_total": availability["workers_total"],
                },
            )

        if task_type in REMINDER_TASK_TYPES:
            text = (prompt or "Reminder").strip()[:500]
            return BackgroundTaskExecutionResult(
                success=True,
                summary=text,
                evidence={"reminder": text},
            )

        return BackgroundTaskExecutionResult(
            success=False,
            summary="Blocked task type",
            error=f"Unsupported task_type: {task_type}",
        )

    @staticmethod
    def sanitize_summary(text: str) -> str:
        lowered = text.lower()
        blocked_tokens = ("token", "secret", "password", "api_key", "nova_cli_", "nova_wrk_")
        if any(token in lowered for token in blocked_tokens):
            return "Background task completed."
        return text[:1000]
