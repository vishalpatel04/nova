"""Model validation and enum tests."""

from nova_core.models.enums import (
    AgentRole,
    ApprovalStatus,
    DeviceCapability,
    DeviceStatus,
    EvidenceBadge,
    MissionStatus,
    MissionStepStatus,
    TimelineEventType,
)


def test_mission_status_values() -> None:
    assert MissionStatus.PENDING.value == "pending"
    assert MissionStatus.QUEUED_WAITING_FOR_WORKER.value == "queued_waiting_for_worker"
    assert MissionStatus.RUNNING.value == "running"
    assert MissionStatus.COMPLETED.value == "completed"
    assert MissionStatus.FAILED.value == "failed"
    assert MissionStatus.CANCELLED.value == "cancelled"
    assert MissionStatus.AWAITING_APPROVAL.value == "awaiting_approval"


def test_device_status_values() -> None:
    assert DeviceStatus.ONLINE.value == "online"
    assert DeviceStatus.OFFLINE.value == "offline"
    assert DeviceStatus.STALE.value == "stale"


def test_approval_status_values() -> None:
    assert ApprovalStatus.PENDING.value == "pending"
    assert ApprovalStatus.APPROVED.value == "approved"


def test_evidence_badge_values() -> None:
    assert EvidenceBadge.VERIFIED.value == "verified"
    assert EvidenceBadge.INFERRED.value == "inferred"


def test_agent_role_values() -> None:
    assert AgentRole.CHIEF_OF_STAFF.value == "chief_of_staff"
    assert AgentRole.SPECIALIST.value == "specialist"


def test_timeline_event_types() -> None:
    assert TimelineEventType.MISSION_CREATED.value == "mission_created"
    assert TimelineEventType.SYSTEM_STATUS.value == "system_status"


def test_device_capabilities() -> None:
    caps = [c.value for c in DeviceCapability]
    assert "shell" in caps
    assert "filesystem" in caps
    assert "ripgrep" in caps
    assert len(caps) == 14


def test_mission_step_status() -> None:
    assert MissionStepStatus.PENDING.value == "pending"
    assert MissionStepStatus.COMPLETED.value == "completed"
