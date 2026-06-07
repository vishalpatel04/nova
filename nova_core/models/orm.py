"""SQLAlchemy ORM models for NOVA control plane."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nova_core.models.database import Base
from nova_core.models.enums import (
    ApprovalStatus,
    DeviceStatus,
    EvidenceBadge,
    MissionStatus,
    MissionStepStatus,
    PairingCodeStatus,
    TokenState,
)


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    devices: Mapped[list["Device"]] = relationship(back_populates="user")
    missions: Mapped[list["Mission"]] = relationship(back_populates="user")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=DeviceStatus.REGISTERED.value)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    architecture: Mapped[str | None] = mapped_column(String(64), nullable=True)
    memory_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpu_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    privacy_class: Mapped[str] = mapped_column(String(32), default="owner")
    token_state: Mapped[str] = mapped_column(String(32), default=TokenState.ACTIVE.value)
    connection_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="devices")
    capabilities: Mapped[list["DeviceCapabilityRecord"]] = relationship(back_populates="device")
    heartbeats: Mapped[list["DeviceHeartbeat"]] = relationship(back_populates="device")


class DeviceCapabilityRecord(Base):
    __tablename__ = "device_capabilities"
    __table_args__ = (UniqueConstraint("device_id", "capability", name="uq_device_capability"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    device: Mapped["Device"] = relationship(back_populates="capabilities")


class DeviceHeartbeat(Base):
    __tablename__ = "device_heartbeats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    device: Mapped["Device"] = relationship(back_populates="heartbeats")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    colour_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    icon_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    voice_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    parent_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    allowed_tool_categories: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    mission_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=MissionStatus.PENDING.value, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="missions")
    steps: Mapped[list["MissionStep"]] = relationship(back_populates="mission")
    agent_messages: Mapped[list["AgentMessage"]] = relationship(back_populates="mission")
    timeline_events: Mapped[list["TimelineEvent"]] = relationship(back_populates="mission")


class MissionStep(Base):
    __tablename__ = "mission_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=MissionStepStatus.PENDING.value)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    input_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mission: Mapped["Mission"] = relationship(back_populates="steps")


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str | None] = mapped_column(
        ForeignKey("missions.id"), nullable=True, index=True
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_badge: Mapped[str] = mapped_column(String(32), default=EvidenceBadge.INFERRED.value)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    mission: Mapped["Mission | None"] = relationship(back_populates="agent_messages")


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str | None] = mapped_column(
        ForeignKey("missions.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sequence_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    stream_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    mission: Mapped["Mission | None"] = relationship(back_populates="timeline_events")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, index=True)
    step_id: Mapped[str | None] = mapped_column(ForeignKey("mission_steps.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=ApprovalStatus.PENDING.value)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer_agent_id: Mapped[str] = mapped_column(String(64), default="neptune")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelUsage(Base):
    __tablename__ = "model_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str | None] = mapped_column(
        ForeignKey("missions.id"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="NOVA Chat")
    provider_mode: Mapped[str] = mapped_column(String(64), default="auto_local_first")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["ChatMessageRecord"]] = relationship(back_populates="session")


class ChatMessageRecord(Base):
    __tablename__ = "chat_message_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    routing: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompanionInboxItem(Base):
    __tablename__ = "companion_inbox_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    source_device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    schedule: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="paused", index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DevicePairingCode(Base):
    __tablename__ = "device_pairing_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=PairingCodeStatus.PENDING.value)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    credential_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default=TokenState.ACTIVE.value)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_from_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceSession(Base):
    __tablename__ = "device_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    credential_id: Mapped[str] = mapped_column(
        ForeignKey("device_credentials.id"), nullable=False, index=True
    )
    connection_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TokenRevocation(Base):
    __tablename__ = "token_revocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    credential_id: Mapped[str] = mapped_column(
        ForeignKey("device_credentials.id"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoked_by: Mapped[str] = mapped_column(String(64), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("principal_id", "scope", "idempotency_key", name="uq_idempotency_scoped"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    principal_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MissionEventSequence(Base):
    __tablename__ = "mission_event_sequences"

    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class QueuedMission(Base):
    __tablename__ = "queued_missions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("missions.id"), nullable=False, unique=True, index=True
    )
    required_device_types: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_by_device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    command_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)


class WorkerCommandAssignment(Base):
    __tablename__ = "worker_command_assignments"

    command_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mission_id: Mapped[str | None] = mapped_column(
        ForeignKey("missions.id"), nullable=True, index=True
    )
    command_type: Mapped[str] = mapped_column(String(64), nullable=False)
    routing_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    target_device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_worker_class: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    assigned_device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stream_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stream_entry_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebSocketTicket(Base):
    __tablename__ = "websocket_tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ticket_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    ticket_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    credential_id: Mapped[str] = mapped_column(
        ForeignKey("device_credentials.id"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    mission_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(32), default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    action_summary: Mapped[str] = mapped_column(String(512), nullable=False)
    command_or_payload_preview: Mapped[str] = mapped_column(Text, nullable=False)
    action_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ShellExecution(Base):
    __tablename__ = "shell_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approval_requests.id"), nullable=False, index=True, unique=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    action_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    command_preview: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stdout_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActiveProject(Base):
    __tablename__ = "active_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_root: Mapped[str] = mapped_column(String(1024), nullable=False)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_tooling: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("device_id", name="uq_active_projects_device_id"),)


class ProjectMemory(Base):
    __tablename__ = "project_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_root: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    last_validation_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_validation_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_patch_proposal: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_task_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recent_task_history: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "device_id", "project_root", name="uq_project_memory_scope"),
    )


class PatchExecution(Base):
    __tablename__ = "patch_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approval_requests.id"), nullable=False, index=True, unique=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    action_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    project_root: Mapped[str] = mapped_column(String(1024), nullable=False)
    patch_preview: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    applied_files: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CodingTask(Base):
    __tablename__ = "coding_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_root: Mapped[str] = mapped_column(String(1024), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_request: Mapped[str] = mapped_column(Text, nullable=False)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    patch_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeline: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
