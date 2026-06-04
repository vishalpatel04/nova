"""Pydantic API request/response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from nova_core.models.enums import (
    AgentRole,
    DeviceStatus,
    EvidenceBadge,
    MissionStatus,
    MissionStepStatus,
)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str


class ReadinessCheck(BaseModel):
    name: str
    status: str
    detail: str | None = None


class ReadinessResponse(BaseModel):
    ready: bool
    checks: list[ReadinessCheck]


class SystemStatusResponse(BaseModel):
    control_plane: str
    database: str
    redis: str
    streaming: str
    workers_online: int
    workers_total: int
    workers_stale: int
    workers_offline: int
    workers_revoked: int
    has_eligible_online_worker: bool
    missions_active: int
    timestamp: datetime


class DeviceResponse(BaseModel):
    id: str
    name: str
    device_type: str
    status: DeviceStatus
    hostname: str | None = None
    os_version: str | None = None
    architecture: str | None = None
    privacy_class: str | None = None
    token_state: str | None = None
    connection_status: str | None = None
    last_seen_at: datetime | None = None
    capabilities: list[str] = Field(default_factory=list)


class AgentResponse(BaseModel):
    id: str
    display_name: str
    role: AgentRole | str
    description: str | None = None
    colour_token: str | None = None
    icon_token: str | None = None
    voice_profile_id: str | None = None
    model_tier: str | None = None
    status: str
    allowed_tool_categories: list[str] = Field(default_factory=list)


class MissionCreateRequest(BaseModel):
    mission_type: str
    title: str
    request_payload: dict[str, Any] | None = None


class MissionStepResponse(BaseModel):
    id: str
    step_order: int
    name: str
    status: MissionStepStatus
    agent_id: str | None = None
    output_payload: dict[str, Any] | None = None


class TimelineEventResponse(BaseModel):
    id: str
    event_type: str
    agent_id: str | None = None
    message: str
    payload: dict[str, Any] | None = None
    created_at: datetime
    sequence_number: int | None = None
    stream_id: str | None = None


class AgentMessageResponse(BaseModel):
    id: str
    agent_id: str
    role: str
    content: str
    evidence_badge: EvidenceBadge
    created_at: datetime


class MissionResponse(BaseModel):
    id: str
    mission_type: str
    status: MissionStatus
    title: str
    request_payload: dict[str, Any] | None = None
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None
    assigned_agent_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steps: list[MissionStepResponse] = Field(default_factory=list)
    timeline_events: list[TimelineEventResponse] = Field(default_factory=list)
    agent_messages: list[AgentMessageResponse] = Field(default_factory=list)


class MissionEventWSMessage(BaseModel):
    event_type: str
    mission_id: str
    message: str
    payload: dict[str, Any] | None = None
    timestamp: datetime


class WorkerRegisterRequest(BaseModel):
    device_id: str
    name: str
    device_type: str
    hostname: str | None = None
    os_version: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class WorkerHeartbeatRequest(BaseModel):
    device_id: str
    status: str = "online"
    payload: dict[str, Any] | None = None


class WorkerRegisterResponse(BaseModel):
    device_id: str
    status: str
    message: str


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiErrorResponse(BaseModel):
    error: ApiErrorDetail
