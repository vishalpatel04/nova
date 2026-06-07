"""Shared enumerations for NOVA domain models."""

from enum import StrEnum


class MissionStatus(StrEnum):
    PENDING = "pending"
    QUEUED_WAITING_FOR_WORKER = "queued_waiting_for_worker"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeviceStatus(StrEnum):
    REGISTERED = "registered"
    ONLINE = "online"
    OFFLINE = "offline"
    STALE = "stale"
    REVOKED = "revoked"
    DECOMMISSIONED = "decommissioned"


class TokenState(StrEnum):
    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"
    EXPIRED = "expired"


class PairingCodeStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    CLAIMED = "claimed"
    EXPIRED = "expired"
    REJECTED = "rejected"


class ConnectionStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"


class PrivacyClass(StrEnum):
    OWNER = "owner"
    TRUSTED = "trusted"
    RESTRICTED = "restricted"
    ISOLATED = "isolated"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class EvidenceBadge(StrEnum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"
    STALE = "stale"


class AgentRole(StrEnum):
    CHIEF_OF_STAFF = "chief_of_staff"
    ENGINEERING_COMMANDER = "engineering_commander"
    PERSONAL_OPS_COMMANDER = "personal_ops_commander"
    RESEARCH_COMMANDER = "research_commander"
    CREATIVE_COMMANDER = "creative_commander"
    MEMORY_COMMANDER = "memory_commander"
    SAFETY_COMMANDER = "safety_commander"
    SPECIALIST = "specialist"


class MissionStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TimelineEventType(StrEnum):
    MISSION_CREATED = "mission_created"
    MISSION_STARTED = "mission_started"
    MISSION_COMPLETED = "mission_completed"
    MISSION_FAILED = "mission_failed"
    MISSION_CANCELLED = "mission_cancelled"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    AGENT_MESSAGE = "agent_message"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    WORKER_HEARTBEAT = "worker_heartbeat"
    SYSTEM_STATUS = "system_status"
    WORKER_COMMAND_DISPATCHED = "worker_command_dispatched"
    WORKER_COMMAND_PICKED_UP = "worker_command_picked_up"
    WORKER_COMMAND_COMPLETED = "worker_command_completed"
    WORKER_COMMAND_FAILED = "worker_command_failed"


class WorkerCommandStatus(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    PICKED_UP = "picked_up"
    COMPLETED = "completed"
    FAILED = "failed"
    STALE_RECOVERED = "stale_recovered"
    CANCELLED = "cancelled"


class WorkerCommandRouting(StrEnum):
    DEVICE = "device"
    WORKER_CLASS = "worker_class"


class DeviceCapability(StrEnum):
    SHELL = "shell"
    FILESYSTEM = "filesystem"
    SPOTLIGHT = "spotlight"
    RIPGREP = "ripgrep"
    GIT = "git"
    GITHUB_CLI = "github_cli"
    CODEX = "codex"
    CURSOR = "cursor"
    OLLAMA = "ollama"
    BROWSER = "browser"
    APPLESCRIPT = "applescript"
    SCREENSHOT = "screenshot"
    DESKTOP_AUTOMATION = "desktop_automation"
    PPT_RENDER = "ppt_render"


class ActionApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class ApprovalRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"


class CodingTaskStage(StrEnum):
    INSPECTING = "inspecting"
    RUNNING_TESTS = "running_tests"
    ANALYZING = "analyzing"
    PATCH_PROPOSED = "patch_proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPLYING_PATCH = "applying_patch"
    RERUNNING_VALIDATION = "rerunning_validation"
    COMPLETED = "completed"
    FAILED = "failed"


class BackgroundTaskType(StrEnum):
    REPO_HEALTH_CHECK = "repo.health_check"
    REPO_RUN_VALIDATION = "repo.run_validation"
    REPO_INSPECT = "repo.inspect"
    PROJECT_SUMMARY = "project.summary"
    SYSTEM_STATUS = "system.status"
    REMINDER_NOTE = "reminder.note"


class BackgroundScheduleKind(StrEnum):
    ONCE = "once"
    INTERVAL = "interval"
    CRON = "cron"


class BackgroundTaskStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class NotificationType(StrEnum):
    TASK_SUCCEEDED = "task.succeeded"
    TASK_FAILED = "task.failed"
    VALIDATION_FAILED = "validation.failed"
    VALIDATION_RECOVERED = "validation.recovered"
    REMINDER = "reminder"
    DRAFT_PLAN_READY = "draft_plan.ready"


class AgentPlanStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentPlanStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    WAITING_APPROVAL = "waiting_approval"


class OrchestrationRole(StrEnum):
    PLANNER = "planner"
    INSPECTOR = "inspector"
    CODER = "coder"
    REVIEWER = "reviewer"
    VALIDATOR = "validator"
    REPORTER = "reporter"


class ProviderLane(StrEnum):
    LOCAL = "local"
    EXTERNAL_RESTRICTED = "external_restricted"


class ReviewerVerdict(StrEnum):
    APPROVED_FOR_USER_REVIEW = "approved_for_user_review"
    NEEDS_REVISION = "needs_revision"
    BLOCKED = "blocked"
