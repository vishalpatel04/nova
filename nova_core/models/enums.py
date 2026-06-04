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
