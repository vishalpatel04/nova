"""Background task type allowlist and metadata."""

from __future__ import annotations

from nova_core.models.enums import BackgroundTaskType

ALLOWED_BACKGROUND_TASK_TYPES: frozenset[str] = frozenset(t.value for t in BackgroundTaskType)

PROJECT_SCOPED_TASK_TYPES: frozenset[str] = frozenset(
    {
        BackgroundTaskType.REPO_HEALTH_CHECK.value,
        BackgroundTaskType.REPO_RUN_VALIDATION.value,
        BackgroundTaskType.REPO_INSPECT.value,
        BackgroundTaskType.PROJECT_SUMMARY.value,
    }
)

SYSTEM_SCOPED_TASK_TYPES: frozenset[str] = frozenset(
    {
        BackgroundTaskType.SYSTEM_STATUS.value,
    }
)

REMINDER_TASK_TYPES: frozenset[str] = frozenset(
    {
        BackgroundTaskType.REMINDER_NOTE.value,
    }
)

MAX_RETRY_ATTEMPTS = 3
BASE_RETRY_SECONDS = 60
