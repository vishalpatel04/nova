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


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    response: str
    intent: str = "general"
    blocked: bool = False
    session_id: str | None = None
    routing: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None
    approval_required: bool = False
    approval_id: str | None = None
    risk_level: str | None = None
    active_project: str | None = None


class ApprovalRequestCreateBody(BaseModel):
    capability: str = Field(min_length=3, max_length=64)
    action_summary: str = Field(min_length=1, max_length=512)
    command_or_payload_preview: str = Field(min_length=1, max_length=4000)
    payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    session_id: str | None = None


class ApprovalRequestResponse(BaseModel):
    id: str
    capability: str
    action_summary: str
    command_or_payload_preview: str
    risk_level: str
    status: str
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    consumed_at: datetime | None = None


class ApprovalPendingListResponse(BaseModel):
    items: list[ApprovalRequestResponse] = Field(default_factory=list)


class RunApprovedExecutionRequest(BaseModel):
    approval_id: str = Field(min_length=36, max_length=36)


class ShellExecutionResponse(BaseModel):
    execution_id: str
    approval_id: str
    capability: str
    command_preview: str
    status: str
    stdout_excerpt: str | None = None
    stderr_excerpt: str | None = None
    exit_code: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ApplyApprovedPatchRequest(BaseModel):
    approval_id: str = Field(min_length=36, max_length=36)


class PatchExecutionResponse(BaseModel):
    execution_id: str
    approval_id: str
    capability: str
    project_root: str
    patch_preview: str
    status: str
    applied_files: list[str] = Field(default_factory=list)
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SetActiveProjectRequest(BaseModel):
    project_root: str = Field(min_length=1, max_length=1024)


class ActiveProjectResponse(BaseModel):
    project_root: str
    project_name: str
    current_branch: str | None = None
    detected_tooling: dict[str, Any] = Field(default_factory=dict)
    last_opened_at: datetime
    user_id: str
    device_id: str


class RunValidationResponse(BaseModel):
    command: str
    exit_code: int
    stdout_excerpt: str
    stderr_excerpt: str
    blocked: bool = False
    block_reason: str | None = None


class CodingTaskResponse(BaseModel):
    task_id: str
    stage: str
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None
    approval_id: str | None = None
    message: str | None = None
    patch_preview: str | None = None
    unified_diff: str | None = None


class ApprovalActionableListResponse(BaseModel):
    pending: list[ApprovalRequestResponse] = Field(default_factory=list)
    approved: list[ApprovalRequestResponse] = Field(default_factory=list)


class ChatMessageRecordResponse(BaseModel):
    id: str
    role: str
    content: str
    intent: str | None = None
    blocked: bool = False
    routing: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None
    created_at: datetime


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    provider_mode: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageRecordResponse] = Field(default_factory=list)


class ProviderHealthResponse(BaseModel):
    provider: str
    configured: bool
    paid: bool
    healthy: bool
    mode: str
    detail: str | None = None


class RuntimeStatusResponse(BaseModel):
    local_first: bool
    paid_providers_enabled: bool
    providers: list[ProviderHealthResponse]
    local_model: str | None = None
    ollama_reachable: bool = False
    ollama_model_ready: bool = False
    provider_badge: str | None = None
    status_message: str | None = None


class AutomationExecuteRequest(BaseModel):
    provider: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    approval_id: str | None = None
    dry_run: bool = False


class AutomationRunResponse(BaseModel):
    id: str
    provider: str
    action: str
    status: str
    requires_approval: bool
    approval_id: str | None = None
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ScheduledTaskCreateRequest(BaseModel):
    title: str
    provider: str
    action: str
    schedule: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ScheduledTaskResponse(BaseModel):
    id: str
    title: str
    provider: str
    action: str
    schedule: str
    status: str
    created_at: datetime


class CompanionPromptRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    target_device_id: str | None = None


class CompanionPromptResponse(BaseModel):
    status: str
    session_id: str
    message_id: str
    inbox_item_id: str | None = None


class CompanionInboxItemResponse(BaseModel):
    id: str
    source_device_id: str | None = None
    target_device_id: str
    message: str
    status: str
    session_id: str | None = None
    message_id: str | None = None
    created_at: datetime
    delivered_at: datetime | None = None
    read_at: datetime | None = None


class ChatStreamCancelResponse(BaseModel):
    stream_id: str
    cancelled: bool


class SchedulerStatusResponse(BaseModel):
    paused: bool
    task_count: int
    tasks: list[dict[str, Any]] = Field(default_factory=list)


class SchedulerTickResponse(BaseModel):
    executed: bool
    paused: bool
    task_count: int
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: str


class BackgroundTaskCreateRequest(BaseModel):
    task_type: str
    title: str
    prompt: str | None = None
    project_root: str | None = None
    schedule_kind: str
    schedule_expression: str


class BackgroundTaskResponse(BaseModel):
    id: str
    user_id: str
    device_id: str
    project_root: str | None
    task_type: str
    title: str
    prompt: str | None
    schedule_kind: str
    schedule_expression: str
    status: str
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_result_summary: str | None
    last_error: str | None
    run_count: int
    failure_count: int
    created_at: datetime
    updated_at: datetime


class BackgroundTaskListResponse(BaseModel):
    tasks: list[BackgroundTaskResponse] = Field(default_factory=list)


class BackgroundTaskRunResponse(BaseModel):
    id: str
    task_id: str
    user_id: str
    device_id: str
    status: str
    summary: str | None
    error: str | None
    evidence_json: dict[str, Any] | None
    attempt: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class BackgroundTaskRunListResponse(BaseModel):
    runs: list[BackgroundTaskRunResponse] = Field(default_factory=list)


class NotificationItemResponse(BaseModel):
    id: str
    user_id: str
    device_id: str
    notification_type: str
    title: str
    summary: str
    task_id: str | None
    read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[NotificationItemResponse] = Field(default_factory=list)
    unread_count: int = 0


class BackgroundSchedulerStatusResponse(BaseModel):
    active: bool
    active_tasks: int
    failed_tasks: int
    due_tasks: int
    unread_notifications: int = 0
