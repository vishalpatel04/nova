"""Chat command routing and safe tool orchestration."""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.agent_mission_service import (
    AgentMissionService,
    is_agent_os_mission_request,
    is_memory_status_request,
    is_preview_request,
    is_system_memory_status_request,
    parse_archive_search_query,
    resolve_deployment_chat_intent,
)
from apps.api.services.agent_plans import AgentPlanService
from apps.api.services.approvals import ApprovalRequestService
from apps.api.services.background_scheduler import BackgroundSchedulerService
from apps.api.services.background_tasks import BackgroundTaskService
from apps.api.services.coding_tasks import CodingTaskService
from apps.api.services.devices import DeviceService
from apps.api.services.git_workflow import GitWorkflowService
from apps.api.services.memory_kernel import MemoryKernelService
from apps.api.services.missions import MissionService
from apps.api.services.notifications import NotificationService
from apps.api.services.orbit_email_service import OrbitEmailService
from apps.api.services.pending_tool_intents import PendingToolIntentService
from apps.api.services.projects import ProjectService
from apps.api.services.runtime import (
    ChatSessionService,
    RuntimeTelemetryService,
    UserMemoryService,
)
from nova_core.agent_os.chat_payload import build_agent_os_chat_payload
from nova_core.agent_os.models import AgentMission
from nova_core.auth.principal import Principal
from nova_core.background.schedules import daily_cron_at
from nova_core.capabilities.model import (
    APPROVAL_REQUIRED_CAPABILITIES,
    PERMANENTLY_BLOCKED_CAPABILITIES,
    CapabilityName,
    risk_for_capability,
)
from nova_core.capabilities.resolver import (
    ActionResolution,
    cloud_file_resolution,
    resolve_chat_message,
)
from nova_core.devices.availability import get_worker_availability
from nova_core.memory.access_policy import AccessProfile
from nova_core.memory.project_history import (
    format_last_failure,
    format_open_loops,
    format_yesterday_summary,
    remember_project_decision,
)
from nova_core.memory.retrieval import build_memory_prompt_section
from nova_core.models.enums import (
    BackgroundScheduleKind,
    BackgroundTaskType,
    MissionStatus,
    PendingToolIntentStatus,
    PendingToolIntentType,
)
from nova_core.models.orm import ChatMessageRecord, Mission
from nova_core.orbit.email_intent import parse_email_draft_request, resolve_email_send_intent
from nova_core.orchestration.app_request import parse_app_request
from nova_core.orchestration.app_spec_clarification import (
    build_clarification_message,
    is_assumption_continuation,
    is_vague_app_request,
    merge_request_with_answers,
)
from nova_core.project.inspect import format_inspection, inspect_repo
from nova_core.project.validation import pick_validation_command, run_validation_command
from nova_core.providers.router import ProviderConfig, ProviderRouter
from nova_core.providers.runtime import InferenceRequest, ProviderRuntime, token_usage_dict
from nova_core.providers.stream_context import StreamCancelToken, StreamTelemetry
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
from nova_core.tools.code_runtime import CodeRuntime
from nova_core.tools.pending_search import (
    parse_scope_confirmation_reply,
    scope_confirmation_prompt,
    unrelated_pending_message,
)
from nova_core.tools.personal_search import PersonalSearchTool, format_search_results
from nova_core.tools.policy import BLOCKED_MESSAGE, ToolDecision, ToolPolicy
from nova_core.tools.protected_paths import (
    PROTECTED_PATH_MESSAGE,
    is_protected_path,
    sanitize_path_for_log,
)
from nova_core.tools.provider_security import (
    FileTransmissionDecision,
    evaluate_file_transmission,
    is_cloud_provider,
    scrub_runtime_detail,
)
from nova_core.tools.safe_readonly import SafeReadonlyTools
from nova_core.tools.search_scopes import resolve_search_scope

HELP_TEXT = """NOVA commands:
- set project <path> — set active coding project
- current project — show active project
- inspect repo — inspect active project
- summarize repo — short project summary
- run validation — run safe test/lint command
- fix failing tests — multi-agent orchestration plan (approval required)
- create coding plan — start bounded agent orchestration
- show active plan / show plan steps — orchestration status
- cancel plan / retry failed step — orchestration controls
- inspect this repo and propose a patch — orchestration workflow
- which provider lane is active? — trust lane status
- propose commit / create approved branch / commit approved changes — git workflow
- show task history — recent project task history
- background tasks — list scheduled background tasks
- create daily repo check at 9am — schedule daily health check
- create repo validation every 6 hours — schedule validation
- pause task <id> / resume task <id> / cancel task <id>
- run task <id> now — trigger immediate safe run
- notifications — show notification inbox
- show failed background tasks — list failed tasks
- summarize latest task run — last run summary
- system status — control plane and worker summary
- connected devices — paired devices list
- worker status — worker online/stale/offline counts
- recent missions — last missions
- list directory [path] — read-only allowlisted directory listing
- read file <path> — read allowlisted file (max 64KB)
- search <pattern> — search active project
- search <pattern> in ~/Downloads|~/Documents|~/Desktop|~/Projects — read-only folder search
- search all approved folders for <pattern> — search Desktop, Documents, Downloads, Projects
- search my computer for <pattern> — prompts to search approved folders
- remember that <fact> — save a user-approved memory
- what do you remember about me? — list saved memory
- what do you remember about <topic>? — search local memory
- search my memory for <topic> — hybrid local memory search
- memory status — local indexing and embedding health
- enable broad local knowledge — index entire home (except NOVA_VAULT)
- index my Mac — bounded local scan
- pause indexing / resume indexing — control background indexer
- show project history — project timeline from memory events
- continue from yesterday / what did we do yesterday? — recent project activity
- export my memory locally — JSON export (local only)
- forget <memory key> — delete saved memory
- forget everything about <topic> — purge topic from local memory
- help — this message

Patch apply requires separate approval + Apply Approved Patch action.
Background tasks never auto-apply patches. Protected paths always blocked."""

MAX_RECENT_CHAT_MESSAGES = 16
MAX_MEMORY_LINES = 5
MAX_MEMORY_CHUNKS = 5
MAX_MEMORY_RELATIONSHIPS = 8
MAX_CONTEXT_CHARS = 6000


@dataclass(frozen=True)
class PathGuardResult:
    allowed: bool
    blocked_message: str | None = None
    approval_resolution: ActionResolution | None = None


class ChatService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._policies = settings.load_yaml("policies.yaml")
        self._policy = ToolPolicy(self._policies)
        safe_cfg = self._policies.get("safe_filesystem", {})
        roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None
        search_roots = safe_cfg.get("search_roots") if isinstance(safe_cfg, dict) else None
        self._search_roots = search_roots
        self._safe_tools = SafeReadonlyTools(allowed_roots=roots)
        self._personal_search = PersonalSearchTool(search_roots=search_roots)
        self._code_runtime = CodeRuntime(allowed_roots=roots)
        self._router = ProviderRouter(ProviderConfig())
        self._provider_runtime = ProviderRuntime(settings)
        self._approval_svc = ApprovalRequestService(session, settings)
        self._last_task_meta: dict[str, Any] | None = None
        self._last_agent_mission_id: str | None = None
        self._last_agent_mission_meta: dict[str, Any] | None = None
        self._last_orbit_email_meta: dict[str, Any] | None = None
        self._pending_active_project: str | None = None
        self._pending_tool_intent_type: str | None = None

    def _intent_handlers(self) -> dict[str, Callable[..., Awaitable[str]]]:
        return {
            "system_status": self._system_status,
            "devices": self._connected_devices,
            "worker_status": self._worker_status,
            "recent_missions": self._recent_missions,
            "create_system_status_mission": self._create_system_status_mission,
            "capabilities": self._worker_capabilities,
            "list_directory": self._list_directory,
            "read_file": self._read_file,
            "ripgrep_search": self._safe_search,
            "safe_search": self._safe_search,
            "search_computer_prompt": self._search_computer_prompt,
            "repo_analysis": self._repo_analysis,
            "explain_code": self._explain_code,
            "patch_plan": self._patch_plan,
            "set_project": self._set_project,
            "current_project": self._current_project,
            "inspect_repo": self._inspect_repo,
            "summarize_repo": self._summarize_repo,
            "run_validation": self._run_validation,
            "coding_task": self._coding_task,
            "background_tasks": self._background_tasks,
            "create_background_task": self._create_background_task,
            "pause_background_task": self._pause_background_task,
            "resume_background_task": self._resume_background_task,
            "cancel_background_task": self._cancel_background_task,
            "run_background_task": self._run_background_task,
            "notifications": self._notifications_list,
            "failed_background_tasks": self._failed_background_tasks,
            "summarize_latest_run": self._summarize_latest_run,
            "orchestration_plan": self._orchestration_plan,
            "show_active_plan": self._show_active_plan,
            "show_plan_steps": self._show_active_plan,
            "cancel_plan": self._cancel_plan,
            "retry_plan_step": self._retry_plan_step,
            "provider_lane": self._provider_lane,
            "external_provider_request": self._external_provider_request,
            "propose_commit": self._propose_commit,
            "create_branch": self._create_branch,
            "commit_changes": self._commit_changes,
            "task_history": self._task_history,
            "memory_summary": self._memory_summary,
            "remember_memory": self._remember_memory,
            "forget_memory": self._forget_memory,
            "memory_lookup": self._memory_lookup,
            "memory_enable_broad": self._memory_enable_broad,
            "memory_disable_broad": self._memory_disable_broad,
            "memory_status": self._memory_status,
            "memory_index_mac": self._memory_index_mac,
            "memory_pause_indexing": self._memory_pause_indexing,
            "memory_resume_indexing": self._memory_resume_indexing,
            "memory_index_progress": self._memory_index_progress,
            "memory_search": self._memory_search,
            "memory_recall": self._memory_recall,
            "memory_forget_topic": self._memory_forget_topic,
            "memory_forget_id": self._memory_forget_id,
            "memory_export": self._memory_export,
            "memory_find_files": self._memory_find_files,
            "project_history": self._project_history,
            "project_yesterday": self._project_yesterday,
            "project_last_failure": self._project_last_failure,
            "project_open_loops": self._project_open_loops,
            "project_remember_decision": self._project_remember_decision,
            "archive_search": self._archive_search,
            "agent_os_mission": self._agent_os_mission,
            "agent_os_mission_status": self._agent_os_mission_status,
            "agent_os_timeline": self._agent_os_timeline,
            "agent_os_approve_deploy": self._agent_os_approve_deploy,
            "agent_os_deploy_yes": self._agent_os_deploy_yes,
            "agent_os_deploy_no": self._agent_os_deploy_no,
            "agent_os_preview": self._agent_os_preview,
            "system_memory_status": self._system_memory_status,
            "orbit_email_draft": self._orbit_email_draft,
            "orbit_email_send_yes": self._orbit_email_send_yes,
            "orbit_email_send_no": self._orbit_email_send_no,
            "orbit_email_send_blocked": self._orbit_email_send_blocked,
        }

    async def handle_message(
        self,
        *,
        message: str,
        principal: Principal,
        session_id: str | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        text = message.strip()
        if not text:
            return self._response("Please enter a message.", intent="empty")

        sessions = ChatSessionService(self.session)
        chat_session = await sessions.get_or_create(principal, session_id, title=self._title(text))
        await sessions.append_message(chat_session, role="user", content=text)

        capability_response = await self._evaluate_capability_action(
            text, principal, chat_session.id
        )
        if capability_response is not None:
            await self._persist_assistant(sessions, chat_session, capability_response)
            return capability_response

        routing = self._router.route(text, intent="general")

        pending_tool_response = await self._try_resolve_pending_tool_intent(
            principal,
            text,
            chat_session.id,
            routing=routing,
        )
        if pending_tool_response is not None:
            await self._persist_assistant(sessions, chat_session, pending_tool_response)
            return pending_tool_response

        orbit_email_svc = OrbitEmailService(self.settings)
        email_intent = resolve_email_send_intent(
            text,
            awaiting=orbit_email_svc.latest_awaiting_send() is not None,
        )
        if email_intent is not None:
            intent_name, email_args = email_intent
            handler = self._intent_handlers().get(intent_name)
            if handler:
                body = await handler(
                    principal, email_args, routing=routing, session_id=chat_session.id
                )
                extra = self._collect_handler_extra(intent_name)
                response = self._response(
                    body,
                    intent=intent_name,
                    routing=routing,
                    session_id=chat_session.id,
                    **extra,
                )
                await self._persist_assistant(sessions, chat_session, response)
                return response

        deploy_intent = resolve_deployment_chat_intent(text)
        if deploy_intent is not None:
            intent_name, deploy_args = deploy_intent
            handler = self._intent_handlers().get(intent_name)
            if handler:
                body = await handler(
                    principal, deploy_args, routing=routing, session_id=chat_session.id
                )
                extra = self._collect_handler_extra(intent_name)
                response = self._response(
                    body,
                    intent=intent_name,
                    routing=routing,
                    session_id=chat_session.id,
                    **extra,
                )
                await self._persist_assistant(sessions, chat_session, response)
                return response

        app_spec_response = await self._try_resolve_pending_app_spec(
            principal,
            text,
            chat_session.id,
            routing=routing,
        )
        if app_spec_response is not None:
            await self._persist_assistant(sessions, chat_session, app_spec_response)
            return app_spec_response

        intent, args = self._parse_intent(text)
        routing = self._router.route(text, intent=intent)

        if intent in {"agent_os_deploy_yes", "agent_os_deploy_no"}:
            pending_response = await self._try_resolve_pending_tool_intent(
                principal,
                text,
                chat_session.id,
                routing=routing,
            )
            if pending_response is not None:
                await self._persist_assistant(sessions, chat_session, pending_response)
                return pending_response

        if intent == "help":
            response = self._response(
                HELP_TEXT, intent=intent, routing=routing, session_id=chat_session.id
            )
            await self._persist_assistant(sessions, chat_session, response)
            return response

        if intent == "blocked":
            await self._audit_blocked(principal, text, reason="blocked_intent")
            response = self._blocked_response(session_id=chat_session.id)
            await self._persist_assistant(sessions, chat_session, response)
            return response

        handler = self._intent_handlers().get(intent)

        if handler and intent != "general":
            await PendingToolIntentService(self.session).cancel_active_for_session(
                principal, chat_session.id
            )

        if handler:
            body = await handler(principal, args, routing=routing, session_id=chat_session.id)
            if body.startswith("Blocked:"):
                response = self._response(
                    body,
                    intent="blocked",
                    routing=routing,
                    blocked=True,
                    session_id=chat_session.id,
                )
                await self._persist_assistant(sessions, chat_session, response)
                return response
            if body.startswith("I can do this after approval."):
                approval_id = self._extract_approval_id(body)
                task_extra: dict[str, Any] = {}
                if self._last_task_meta:
                    task_extra = {
                        k: self._last_task_meta.get(k)
                        for k in (
                            "task_id",
                            "timeline",
                            "unified_diff",
                            "patch_preview",
                            "active_project",
                        )
                        if self._last_task_meta.get(k) is not None
                    }
                    self._last_task_meta = None
                response = self._response(
                    body,
                    intent="approval_required",
                    routing=routing,
                    blocked=False,
                    session_id=chat_session.id,
                    approval_required=True,
                    approval_id=approval_id or task_extra.pop("approval_id", None),
                    **task_extra,
                )
                await self._persist_assistant(sessions, chat_session, response)
                return response
            await self._maybe_audit_command(principal, intent, args, body)
            extra = self._collect_handler_extra(intent)
            response = self._response(
                body,
                intent=intent,
                routing=routing,
                session_id=chat_session.id,
                **extra,
            )
            await self._persist_assistant(sessions, chat_session, response)
            return response

        pending_response = await self._try_resolve_pending_tool_intent(
            principal,
            text,
            chat_session.id,
            routing=routing,
        )
        if pending_response is not None:
            await self._persist_assistant(sessions, chat_session, pending_response)
            return pending_response

        response = await self._general_chat_response(
            principal,
            chat_session,
            text,
            intent=intent,
            routing=routing,
            stream=stream,
        )
        await self._persist_assistant(sessions, chat_session, response)
        return response

    async def stream_message(
        self,
        *,
        message: str,
        principal: Principal,
        session_id: str | None = None,
        cancel: StreamCancelToken | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        text = message.strip()
        sessions = ChatSessionService(self.session)
        if not text:
            yield {"event": "error", "data": {"message": "Please enter a message."}}
            return

        chat_session = await sessions.get_or_create(principal, session_id, title=self._title(text))
        await sessions.append_message(chat_session, role="user", content=text)
        yield {
            "event": "session",
            "data": {
                "session_id": chat_session.id,
                "stream_id": cancel.stream_id if cancel else None,
            },
        }

        capability_response = await self._evaluate_capability_action(
            text, principal, chat_session.id
        )
        if capability_response is not None:
            async for event in self._emit_full_response(
                sessions, chat_session, capability_response
            ):
                if cancel and cancel.cancelled:
                    yield {"event": "cancelled", "data": {}}
                    return
                yield event
            return

        routing = self._router.route(text, intent="general")

        pending_tool_response = await self._try_resolve_pending_tool_intent(
            principal,
            text,
            chat_session.id,
            routing=routing,
        )
        if pending_tool_response is not None:
            async for event in self._emit_full_response(
                sessions, chat_session, pending_tool_response
            ):
                if cancel and cancel.cancelled:
                    yield {"event": "cancelled", "data": {}}
                    return
                yield event
            return

        orbit_email_svc = OrbitEmailService(self.settings)
        email_intent = resolve_email_send_intent(
            text,
            awaiting=orbit_email_svc.latest_awaiting_send() is not None,
        )
        if email_intent is not None:
            intent_name, email_args = email_intent
            handler = self._intent_handlers().get(intent_name)
            if handler:
                body = await handler(
                    principal, email_args, routing=routing, session_id=chat_session.id
                )
                extra = self._collect_handler_extra(intent_name)
                response = self._response(
                    body,
                    intent=intent_name,
                    routing=routing,
                    session_id=chat_session.id,
                    **extra,
                )
                async for event in self._emit_full_response(sessions, chat_session, response):
                    if cancel and cancel.cancelled:
                        yield {"event": "cancelled", "data": {}}
                        return
                    yield event
                return

        deploy_intent = resolve_deployment_chat_intent(text)
        if deploy_intent is not None:
            intent_name, deploy_args = deploy_intent
            handler = self._intent_handlers().get(intent_name)
            if handler:
                body = await handler(
                    principal, deploy_args, routing=routing, session_id=chat_session.id
                )
                extra = self._collect_handler_extra(intent_name)
                response = self._response(
                    body,
                    intent=intent_name,
                    routing=routing,
                    session_id=chat_session.id,
                    **extra,
                )
                async for event in self._emit_full_response(sessions, chat_session, response):
                    if cancel and cancel.cancelled:
                        yield {"event": "cancelled", "data": {}}
                        return
                    yield event
                return

        app_spec_response = await self._try_resolve_pending_app_spec(
            principal,
            text,
            chat_session.id,
            routing=routing,
        )
        if app_spec_response is not None:
            async for event in self._emit_full_response(sessions, chat_session, app_spec_response):
                if cancel and cancel.cancelled:
                    yield {"event": "cancelled", "data": {}}
                    return
                yield event
            return

        intent, args = self._parse_intent(text)
        routing = self._router.route(text, intent=intent)

        if intent in {"agent_os_deploy_yes", "agent_os_deploy_no"}:
            pending_response = await self._try_resolve_pending_tool_intent(
                principal,
                text,
                chat_session.id,
                routing=routing,
            )
            if pending_response is not None:
                async for event in self._emit_full_response(
                    sessions, chat_session, pending_response
                ):
                    if cancel and cancel.cancelled:
                        yield {"event": "cancelled", "data": {}}
                        return
                    yield event
                return

        if intent == "help":
            response = self._response(
                HELP_TEXT, intent=intent, routing=routing, session_id=chat_session.id
            )
            async for event in self._emit_full_response(sessions, chat_session, response):
                if cancel and cancel.cancelled:
                    yield {"event": "cancelled", "data": {}}
                    return
                yield event
            return

        if intent == "blocked":
            await self._audit_blocked(principal, text, reason="blocked_intent")
            response = self._blocked_response(session_id=chat_session.id)
            async for event in self._emit_full_response(sessions, chat_session, response):
                if cancel and cancel.cancelled:
                    yield {"event": "cancelled", "data": {}}
                    return
                yield event
            return

        handler = self._intent_handlers().get(intent)

        if handler and intent != "general":
            await PendingToolIntentService(self.session).cancel_active_for_session(
                principal, chat_session.id
            )

        if handler:
            body = await handler(principal, args, routing=routing, session_id=chat_session.id)
            if body.startswith("Blocked:"):
                response = self._response(
                    body,
                    intent="blocked",
                    routing=routing,
                    blocked=True,
                    session_id=chat_session.id,
                )
            elif body.startswith("I can do this after approval."):
                response = self._response(
                    body,
                    intent="approval_required",
                    routing=routing,
                    blocked=False,
                    session_id=chat_session.id,
                    approval_required=True,
                    approval_id=self._extract_approval_id(body),
                )
            else:
                await self._maybe_audit_command(principal, intent, args, body)
                extra = self._collect_handler_extra(intent)
                response = self._response(
                    body,
                    intent=intent,
                    routing=routing,
                    session_id=chat_session.id,
                    **extra,
                )
            async for event in self._emit_full_response(sessions, chat_session, response):
                if cancel and cancel.cancelled:
                    yield {"event": "cancelled", "data": {}}
                    return
                yield event
            return

        pending_response = await self._try_resolve_pending_tool_intent(
            principal,
            text,
            chat_session.id,
            routing=routing,
        )
        if pending_response is not None:
            async for event in self._emit_full_response(sessions, chat_session, pending_response):
                if cancel and cancel.cancelled:
                    yield {"event": "cancelled", "data": {}}
                    return
                yield event
            return

        prompt, context_meta = await self._build_general_prompt(principal, chat_session, text)
        telemetry = StreamTelemetry(stream_id=cancel.stream_id if cancel else "inline")
        content_parts: list[str] = []
        inference_request = InferenceRequest(prompt=prompt, intent=intent, stream=True)
        stream_fn = self._provider_runtime.stream
        stream_kwargs: dict[str, Any] = {"cancel": cancel}
        if "telemetry" in inspect.signature(stream_fn).parameters:
            stream_kwargs["telemetry"] = telemetry
        async for chunk in stream_fn(
            inference_request,
            **stream_kwargs,
        ):
            if cancel and cancel.cancelled:
                telemetry.cancelled = True
                yield {"event": "cancelled", "data": {}}
                await self._persist_partial_assistant(
                    sessions,
                    chat_session,
                    "".join(content_parts),
                    intent="general",
                    routing=routing,
                    cancelled=True,
                )
                return
            content_parts.append(chunk)
            yield {"event": "token", "data": {"delta": chunk}}

        if cancel and cancel.cancelled:
            telemetry.cancelled = True
            yield {"event": "cancelled", "data": {}}
            await self._persist_partial_assistant(
                sessions,
                chat_session,
                "".join(content_parts),
                intent="general",
                routing=routing,
                cancelled=True,
            )
            return

        content = "".join(content_parts).strip() or self._provider_runtime._default_help()
        usage = {
            "provider": telemetry.provider or "local",
            "model": telemetry.model or "streamed",
            "input_tokens": self._provider_runtime._estimate_tokens(prompt),
            "output_tokens": self._provider_runtime._estimate_tokens(content),
            "mode": telemetry.mode or "stream",
            "fallback_used": telemetry.fallback_used,
            "fallback_reason": telemetry.fallback_reason,
            "error": telemetry.fallback_reason,
        }
        response = self._response(
            content,
            intent="general",
            routing=routing,
            session_id=chat_session.id,
            token_usage=usage,
            runtime_mode=telemetry.mode or ("degraded" if telemetry.fallback_reason else "local"),
            selected_provider=telemetry.provider or "local",
            selected_model=telemetry.model or "streamed",
            fallback_reason=telemetry.fallback_reason,
            local_available=context_meta.get("local_available"),
        )
        await self._persist_assistant(sessions, chat_session, response)
        yield {
            "event": "done",
            "data": {
                "response": response["response"],
                "intent": response["intent"],
                "blocked": response["blocked"],
                "session_id": chat_session.id,
                "token_usage": usage,
                "routing": response.get("routing"),
                "runtime_mode": response.get("runtime_mode"),
                "selected_provider": response.get("selected_provider"),
                "selected_model": response.get("selected_model"),
                "fallback_reason": response.get("fallback_reason"),
                "local_available": response.get("local_available"),
            },
        }

    async def _emit_full_response(
        self,
        sessions: ChatSessionService,
        chat_session: Any,
        response: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        body = str(response["response"])
        if response.get("agent_os_mission"):
            if response.get("intent") == "agent_os_mission":
                yield {"event": "token", "data": {"delta": "Running Agent OS mission…\n"}}
            await self._persist_assistant(sessions, chat_session, response)
            yield {
                "event": "done",
                "data": self._stream_done_payload(response),
            }
            return
        if response.get("orbit_email_draft"):
            await self._persist_assistant(sessions, chat_session, response)
            yield {
                "event": "done",
                "data": self._stream_done_payload(response),
            }
            return
        chunk_size = 24
        for index in range(0, len(body), chunk_size):
            yield {"event": "token", "data": {"delta": body[index : index + chunk_size]}}
            await asyncio.sleep(0.005)
        await self._persist_assistant(sessions, chat_session, response)
        yield {
            "event": "done",
            "data": self._stream_done_payload(response),
        }

    def _stream_done_payload(self, response: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "intent": response.get("intent", "general"),
            "blocked": bool(response.get("blocked", False)),
            "session_id": response.get("session_id"),
            "token_usage": response.get("token_usage"),
            "routing": response.get("routing"),
            "active_project": response.get("active_project"),
            "pending_tool_intent": response.get("pending_tool_intent"),
            "response": response.get("response"),
            "runtime_mode": response.get("runtime_mode"),
            "selected_provider": response.get("selected_provider"),
            "selected_model": response.get("selected_model"),
            "fallback_reason": response.get("fallback_reason"),
            "local_available": response.get("local_available"),
        }
        if response.get("agent_os_mission"):
            payload["agent_os_mission"] = response["agent_os_mission"]
        if response.get("orbit_email_draft"):
            payload["orbit_email_draft"] = response["orbit_email_draft"]
        if response.get("task_id"):
            payload["task_id"] = response["task_id"]
        if response.get("timeline"):
            payload["timeline"] = response["timeline"]
        return payload

    async def _persist_partial_assistant(
        self,
        sessions: ChatSessionService,
        chat_session: Any,
        content: str,
        *,
        intent: str,
        routing: Any | None,
        cancelled: bool,
    ) -> None:
        if not content.strip():
            return
        await sessions.append_message(
            chat_session,
            role="assistant",
            content=content,
            intent=intent,
            blocked=False,
            routing={
                "cancelled": cancelled,
                "provider": routing.provider.value if routing else None,
                "mode": routing.mode if routing else None,
            }
            if routing
            else {"cancelled": cancelled},
        )
        await self.session.commit()

    def _parse_intent(self, text: str) -> tuple[str, dict[str, str]]:
        lowered = text.lower().strip()

        if lowered in {"help", "?", "commands", "what can you do", "what can you do?"}:
            return "help", {}

        if lowered in {"system status", "status", "system_status"}:
            return "system_status", {}

        if is_system_memory_status_request(text):
            return "system_memory_status", {}

        if is_memory_status_request(text):
            return "memory_status", {}

        email_draft = parse_email_draft_request(text)
        if email_draft is not None:
            return "orbit_email_draft", {"request": text.strip()}

        if is_agent_os_mission_request(text):
            return "agent_os_mission", {"request": text.strip()}

        deploy_intent = resolve_deployment_chat_intent(text)
        if deploy_intent is not None:
            return deploy_intent

        if is_preview_request(text):
            return "agent_os_preview", {}

        if lowered in {"show agent timeline", "agent timeline"}:
            return "agent_os_timeline", {}

        if lowered in {"mission status", "show mission status"}:
            return "agent_os_mission_status", {}

        if lowered in {"approve deployment", "approve deploy"}:
            return "agent_os_approve_deploy", {}

        archive_query = parse_archive_search_query(text)
        if archive_query is not None:
            return "archive_search", {"query": archive_query}

        recall_match = re.match(r"^what do you remember about (.+?)\??$", text, re.I)
        if recall_match and recall_match.group(1).strip().lower() not in {"me", "myself"}:
            topic = recall_match.group(1).strip()
            if "from my files" not in topic.lower():
                return "memory_recall", {"topic": topic}

        if lowered in {"connected devices", "devices", "list devices"}:
            return "devices", {}

        if lowered in {"worker status", "workers", "worker_status"}:
            return "worker_status", {}

        if lowered in {"recent missions", "missions", "list missions"}:
            return "recent_missions", {}

        if lowered in {
            "create system status mission",
            "create system_status mission",
            "run system status",
            "run system_status",
        }:
            return "create_system_status_mission", {}

        if lowered in {"list worker capabilities", "capabilities", "worker capabilities"}:
            return "capabilities", {}

        if lowered.startswith("list directory"):
            path = text[len("list directory") :].strip() or "."
            return "list_directory", {"path": path}

        if lowered.startswith("read file "):
            return "read_file", {"path": text[10:].strip()}

        if lowered.startswith("search my computer for "):
            pattern = text[len("search my computer for ") :].strip()
            return "archive_search", {"query": pattern}

        if lowered in {"what do you remember about me", "what do you remember about me?"}:
            return "memory_summary", {}

        if lowered.startswith("remember that "):
            return "remember_memory", {"statement": text[len("remember that ") :].strip()}

        if lowered.startswith("remember "):
            return "remember_memory", {"statement": text[len("remember ") :].strip()}

        if lowered.startswith("forget that "):
            return "forget_memory", {"statement": text[len("forget that ") :].strip()}

        if lowered.startswith("forget "):
            return "forget_memory", {"statement": text[len("forget ") :].strip()}

        memory_lookup = self._parse_memory_lookup(text)
        if memory_lookup is not None:
            return "memory_lookup", memory_lookup

        if lowered in {"enable broad local knowledge", "enable broad local"}:
            return "memory_enable_broad", {}

        if lowered in {"disable broad local knowledge", "disable broad local"}:
            return "memory_disable_broad", {}

        if lowered in {"index my mac", "index my mac."}:
            return "memory_index_mac", {}

        if lowered == "pause indexing":
            return "memory_pause_indexing", {}

        if lowered == "resume indexing":
            return "memory_resume_indexing", {}

        if lowered in {"show indexing progress", "indexing progress"}:
            return "memory_index_progress", {}

        if lowered.startswith("search my memory for "):
            return "archive_search", {"query": text[len("search my memory for ") :].strip()}

        if lowered.startswith("forget everything about "):
            return "memory_forget_topic", {"topic": text[len("forget everything about ") :].strip()}

        if lowered.startswith("forget memory "):
            return "memory_forget_id", {"memory_id": text[len("forget memory ") :].strip()}

        if lowered in {"export my memory locally", "export memory", "export my memory"}:
            return "memory_export", {}

        if lowered in {"show project history", "project history"}:
            return "project_history", {}

        if lowered in {
            "continue from yesterday",
            "what did we do yesterday?",
            "what did we do yesterday",
        }:
            return "project_yesterday", {}

        if lowered in {"what broke last time?", "what broke last time"}:
            return "project_last_failure", {}

        if lowered in {"show open loops", "open loops"}:
            return "project_open_loops", {}

        if lowered.startswith("remember this project decision:"):
            return "project_remember_decision", {
                "text": text[len("remember this project decision:") :].strip()
            }

        if lowered.startswith("find my ") and "file" in lowered:
            return "memory_find_files", {"topic": text[len("find my ") :].strip()}

        if lowered.startswith("search my mac for "):
            pattern = text[len("search my mac for ") :].strip()
            return "archive_search", {"query": pattern}

        broad_search = self._parse_broad_personal_search(text)
        if broad_search is not None:
            return "archive_search", {"query": broad_search.get("pattern", "")}

        if lowered.startswith("search all approved folders for "):
            pattern = text[len("search all approved folders for ") :].strip()
            return "safe_search", {"pattern": pattern, "scope": "all_approved"}

        scoped_personal = self._parse_scoped_personal_search(text)
        if scoped_personal is not None:
            return "safe_search", scoped_personal

        if lowered.startswith("search "):
            remainder = text[7:].strip()
            lowered_remainder = remainder.lower()
            if lowered_remainder.startswith("all approved folders for "):
                pattern = remainder[len("all approved folders for ") :].strip()
                return "safe_search", {"pattern": pattern, "scope": "all_approved"}
            if lowered_remainder.startswith("my computer for "):
                pattern = remainder[len("my computer for ") :].strip()
                return "archive_search", {"query": pattern}
            in_match = re.match(r"^(.+?)\s+in\s+(.+)$", remainder, re.I)
            if in_match:
                pattern = in_match.group(1).strip()
                path = in_match.group(2).strip()
                return "safe_search", {"pattern": pattern, "path": path, "scope": "path"}
            pattern = remainder.strip()
            return "safe_search", {"pattern": pattern, "scope": "active_project"}

        if lowered in {"repo analysis", "analyze repo", "analyse repo"}:
            return "repo_analysis", {"path": "~/Projects/nova"}

        if lowered.startswith("explain code "):
            return "explain_code", {"path": text[len("explain code ") :].strip()}

        if lowered.startswith("generate patch "):
            return "patch_plan", {"instruction": text[len("generate patch ") :].strip()}

        if lowered.startswith("set project "):
            return "set_project", {"path": text[len("set project ") :].strip()}

        if lowered in {"current project", "show project", "active project"}:
            return "current_project", {}

        if lowered in {"inspect repo", "inspect repository"}:
            return "inspect_repo", {}

        if lowered in {"summarize repo", "summarize repository", "repo summary"}:
            return "summarize_repo", {}

        if lowered in {"run validation", "validate project", "run tests", "run validation tests"}:
            return "run_validation", {}

        if lowered in {"show active plan", "active plan", "current plan"}:
            return "show_active_plan", {}

        if lowered in {"show plan steps", "plan steps", "plan timeline"}:
            return "show_plan_steps", {}

        if lowered.startswith("cancel plan"):
            plan_id = text[len("cancel plan") :].strip()
            return "cancel_plan", {"plan_id": plan_id}

        retry_match = re.match(r"retry failed step(?: (\d+))?", lowered)
        if retry_match:
            return "retry_plan_step", {"step_index": retry_match.group(1) or "0"}

        if lowered in {
            "create coding plan",
            "create orchestration plan",
        } or lowered.startswith("create coding plan "):
            objective = text.split("create coding plan", 1)[-1].strip() or "Fix failing tests"
            return "orchestration_plan", {"objective": objective}

        if lowered in {
            "which provider lane is active?",
            "which provider lane is active",
            "provider lane",
            "trust lane",
        }:
            return "provider_lane", {}

        if lowered.startswith("enable external provider"):
            return "external_provider_request", {"request": text}

        if lowered.startswith("propose commit"):
            return "propose_commit", {"message": text[len("propose commit") :].strip()}

        if lowered.startswith("create approved branch"):
            branch = text[len("create approved branch") :].strip()
            return "create_branch", {"branch_name": branch}

        if lowered in {"commit approved changes", "commit locally", "commit approved"}:
            return "commit_changes", {}

        if lowered in {"show task history", "task history"}:
            return "task_history", {}

        orchestration_triggers = (
            "inspect this repo and propose a patch",
            "inspect this repo and fix",
            "inspect repo and fix",
        )
        if any(lowered.startswith(t) or t in lowered for t in orchestration_triggers):
            return "orchestration_plan", {"objective": text}

        if lowered in {"background tasks", "list background tasks", "scheduled tasks"}:
            return "background_tasks", {}

        if lowered in {"notifications", "show notifications", "inbox"}:
            return "notifications", {}

        if lowered in {"show failed background tasks", "failed background tasks", "failed tasks"}:
            return "failed_background_tasks", {}

        if lowered in {
            "summarize latest task run",
            "latest task run",
            "summarize task run",
        }:
            return "summarize_latest_run", {}

        daily_match = re.match(
            r"create daily repo check at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
            lowered,
        )
        if daily_match:
            hour = int(daily_match.group(1))
            minute = int(daily_match.group(2) or "0")
            meridiem = daily_match.group(3)
            if meridiem == "pm" and hour < 12:
                hour += 12
            if meridiem == "am" and hour == 12:
                hour = 0
            return "create_background_task", {
                "schedule_kind": BackgroundScheduleKind.CRON.value,
                "schedule_expression": daily_cron_at(hour, minute),
                "task_type": BackgroundTaskType.REPO_HEALTH_CHECK.value,
                "title": f"Daily repo check at {hour:02d}:{minute:02d}",
            }

        interval_match = re.match(
            r"create repo validation every (\d+)\s*(hours?|h|minutes?|m|days?|d)",
            lowered,
        )
        if interval_match:
            amount = interval_match.group(1)
            unit_raw = interval_match.group(2)[0].lower()
            unit = {"h": "h", "m": "m", "d": "d"}.get(unit_raw, "h")
            return "create_background_task", {
                "schedule_kind": BackgroundScheduleKind.INTERVAL.value,
                "schedule_expression": f"{amount}{unit}",
                "task_type": BackgroundTaskType.REPO_RUN_VALIDATION.value,
                "title": f"Repo validation every {amount}{unit}",
            }

        for verb, intent in (
            ("pause task", "pause_background_task"),
            ("resume task", "resume_background_task"),
            ("cancel task", "cancel_background_task"),
        ):
            if lowered.startswith(verb + " "):
                return intent, {"task_id": text[len(verb) + 1 :].strip()}

        run_now_match = re.match(r"run task ([a-f0-9-]+) now", lowered)
        if run_now_match:
            return "run_background_task", {"task_id": run_now_match.group(1)}

        coding_triggers = (
            "fix failing test",
            "fix failing tests",
        )
        if any(lowered.startswith(t) or t in lowered for t in coding_triggers):
            return "orchestration_plan", {"objective": text}

        legacy_coding = (
            "propose patch",
            "analyze this repo",
            "explain this error",
            "explain error",
        )
        if any(lowered.startswith(t) or t in lowered for t in legacy_coding):
            return "coding_task", {"request": text}

        if re.search(r"\b(execute|delete|write file|open browser|n8n)\b", lowered):
            return "blocked", {}
        if re.search(r"\bsend email\b", lowered) and "draft" not in lowered:
            return "blocked", {}

        if re.search(r"\brun\b", lowered) and lowered not in {
            "run system status",
            "run system_status",
        }:
            return "blocked", {}

        return "general", {}

    def _collect_handler_extra(self, intent: str) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if intent == "set_project" and self._pending_active_project:
            extra["active_project"] = self._pending_active_project
            self._pending_active_project = None
        if intent == "coding_task" and self._last_task_meta:
            for key in (
                "task_id",
                "timeline",
                "approval_id",
                "unified_diff",
                "patch_preview",
                "active_project",
            ):
                value = self._last_task_meta.get(key)
                if value is not None:
                    extra[key] = value
            self._last_task_meta = None
        if intent.startswith("orbit_email_") and self._last_orbit_email_meta:
            extra["orbit_email_draft"] = self._last_orbit_email_meta
            if self._last_orbit_email_meta.get("status") == "awaiting_send_approval":
                extra["pending_tool_intent"] = "orbit_email_send"
            self._last_orbit_email_meta = None
        if intent.startswith("agent_os_") and self._last_agent_mission_meta:
            extra["agent_os_mission"] = self._last_agent_mission_meta
            if self._last_agent_mission_meta.get("status") == "waiting_approval":
                extra["pending_tool_intent"] = "agent_os_deploy"
            self._last_agent_mission_meta = None
        if self._pending_tool_intent_type:
            extra["pending_tool_intent"] = self._pending_tool_intent_type
            self._pending_tool_intent_type = None
        return extra

    def _store_agent_mission_payload(self, mission: AgentMission) -> None:
        self._last_agent_mission_id = mission.mission_id
        self._last_agent_mission_meta = build_agent_os_chat_payload(mission)

    @staticmethod
    def _approval_kind_for_mission(mission: AgentMission) -> str:
        runtime = mission.artifacts.get("runtime") or mission.final_report.get("runtime", "web")
        return "package" if runtime == "cli" else "deploy"

    def _approval_recorded_message(self, mission: AgentMission) -> str:
        if self._approval_kind_for_mission(mission) == "package":
            return "Packaging approval recorded.\nPackaging step is prepared/stubbed in this build."
        return (
            "Deployment approval recorded.\n"
            "Vercel deploy integration is prepared but not enabled in this build."
        )

    def _approval_skipped_message(self, mission: AgentMission) -> str:
        is_package = self._approval_kind_for_mission(mission) == "package"
        kind = "Packaging" if is_package else "Deployment"
        return f"{kind} skipped."

    def _parse_scoped_personal_search(self, text: str) -> dict[str, str] | None:
        normalized = re.sub(r"\s+", " ", text.strip())
        folder_map = {
            "downloads": "~/Downloads",
            "download folder": "~/Downloads",
            "my downloads": "~/Downloads",
            "documents": "~/Documents",
            "document folder": "~/Documents",
            "my documents": "~/Documents",
            "desktop": "~/Desktop",
            "my desktop": "~/Desktop",
            "projects": "~/Projects",
            "my projects": "~/Projects",
        }
        patterns = (
            (
                r"^(?:can you |could you |please )?"
                r"(?:search|find|look for|search for|find files related to|"
                r"look for files related to)\s+(?P<pattern>.+?)\s+"
                r"(?:in|inside|under)\s+(?:my\s+)?"
                r"(?P<folder>downloads?|download folder|my downloads|"
                r"documents?|document folder|my documents|desktop|my desktop|"
                r"projects|my projects)(?:\s+folder)?$"
            ),
            (
                r"^(?:can you |could you |please )?"
                r"(?:search|find|look for)\s+(?:my\s+)?"
                r"(?P<folder>downloads?|download folder|my downloads|"
                r"documents?|document folder|my documents|desktop|my desktop|"
                r"projects|my projects)\s+for\s+(?P<pattern>.+)$"
            ),
            (
                r"^search\s+(?P<pattern>.+?)\s+in\s+(?:my\s+)?"
                r"(?P<folder>downloads?|download folder|my downloads|"
                r"documents?|document folder|my documents|desktop|my desktop|"
                r"projects|my projects)(?:\s+folder)?$"
            ),
        )
        for pattern in patterns:
            match = re.match(pattern, normalized, re.I)
            if not match:
                continue
            folder = match.group("folder").lower().strip()
            path = folder_map.get(folder)
            if not path:
                continue
            search_pattern = match.group("pattern").strip()
            if not search_pattern:
                return None
            return {"pattern": search_pattern, "path": path, "scope": "path"}
        return None

    def _parse_broad_personal_search(self, text: str) -> dict[str, str] | None:
        normalized = re.sub(r"\s+", " ", text.strip())
        match = re.match(
            (
                r"^(?:can you |could you |please )?"
                r"(?:search|find|look for)\s+everything related to\s+"
                r"(?P<pattern>.+?)\s+on my mac$"
            ),
            normalized,
            re.I,
        )
        if match:
            return {"pattern": match.group("pattern").strip()}
        match = re.match(
            (
                r"^(?:can you |could you |please )?"
                r"(?:search|find|look for)\s+my computer for\s+(?P<pattern>.+)$"
            ),
            normalized,
            re.I,
        )
        if match:
            return {"pattern": match.group("pattern").strip()}
        return None

    def _parse_memory_lookup(self, text: str) -> dict[str, str] | None:
        normalized = re.sub(r"\s+", " ", text.strip())
        match = re.match(
            (
                r"^where (?:are|is|did i say) (?:my |the )?"
                r"(?P<subject>.+?)(?: usually)? "
                r"(?:stored|kept|located|saved)?\??$"
            ),
            normalized,
            re.I,
        )
        if match:
            return {"subject": match.group("subject").strip()}
        match = re.match(
            (
                r"^where did i say (?:my |the )?"
                r"(?P<subject>.+?) (?:are|is) "
                r"(?:probably|usually)?(?:\s+in|\s+stored in)? "
                r"(?P<location>.+?)\??$"
            ),
            normalized,
            re.I,
        )
        if match:
            return {
                "subject": match.group("subject").strip(),
                "location": match.group("location").strip(),
            }
        return None

    async def _general_chat_response(
        self,
        principal: Principal,
        chat_session: Any,
        text: str,
        *,
        intent: str,
        routing: Any | None,
        stream: bool,
    ) -> dict[str, Any]:
        prompt, context_meta = await self._build_general_prompt(principal, chat_session, text)
        inference = await self._provider_runtime.infer(
            InferenceRequest(prompt=prompt, intent=intent, stream=stream)
        )
        await RuntimeTelemetryService(self.session).record_model_usage(inference)
        usage = token_usage_dict(inference)
        return self._response(
            inference.content.strip() or self._provider_runtime._default_help(),
            intent="general",
            routing=routing,
            session_id=chat_session.id,
            token_usage=usage,
            runtime_mode=inference.mode,
            selected_provider=inference.provider.value,
            selected_model=inference.model,
            fallback_reason=inference.fallback_reason,
            local_available=context_meta.get("local_available"),
        )

    async def _build_general_prompt(
        self,
        principal: Principal,
        chat_session: Any,
        text: str,
    ) -> tuple[str, dict[str, Any]]:
        sessions = ChatSessionService(self.session)
        recent_messages = await sessions.get_recent_messages(
            principal, chat_session.id, limit=MAX_RECENT_CHAT_MESSAGES
        )
        memory_svc = UserMemoryService(self.session)
        memories = await memory_svc.list_memories(principal, limit=MAX_MEMORY_LINES)
        project_svc = ProjectService(self.session, self.settings)
        active_project = await project_svc.get_active_project_or_none(principal)
        kernel = MemoryKernelService(self.session, self.settings)
        retrieval = await kernel.retrieve(
            principal.user_id,
            text,
            session_id=chat_session.id,
            project_root=active_project.project_root if active_project else None,
            limit=MAX_MEMORY_CHUNKS,
        )
        memory_section = build_memory_prompt_section(retrieval, max_chars=1500)

        prompt_lines = [
            "You are NOVA, a concise desktop assistant.",
            "Keep responses short, direct, and practical.",
        ]
        if active_project is not None:
            prompt_lines.append(
                f"Active project: {active_project.project_name} ({active_project.project_root})"
            )
        if memories:
            prompt_lines.append("Remembered facts:")
            for memory in memories[:MAX_MEMORY_LINES]:
                prompt_lines.append(f"- {memory.key}: {memory.value_summary}")
        if memory_section:
            prompt_lines.append(memory_section)
        if recent_messages:
            prompt_lines.append("Recent conversation:")
            for record in recent_messages[-MAX_RECENT_CHAT_MESSAGES:]:
                if self._should_include_prompt_message(record):
                    prompt_lines.append(
                        f"- {record.role}: {self._bounded_prompt_text(record.content)}"
                    )
        prompt_lines.append(f"User: {self._bounded_prompt_text(text)}")
        prompt_lines.append("NOVA:")
        prompt = "\n".join(prompt_lines)
        if len(prompt) > MAX_CONTEXT_CHARS:
            header = "\n".join(prompt_lines[:2])
            tail = "\n".join(prompt_lines[2:])
            prompt = header + "\n" + tail[-max(0, MAX_CONTEXT_CHARS - len(header) - 1) :]
        return prompt, {
            "local_available": bool(
                self.settings.nova_ollama_base_url
                or self.settings.nova_qwen_base_url
                or self.settings.nova_deepseek_base_url
            ),
            "active_project": active_project.project_name if active_project else None,
        }

    def _should_include_prompt_message(self, record: ChatMessageRecord) -> bool:
        return (
            not record.blocked
            and record.role in {"user", "assistant"}
            and record.intent
            not in {"read_file", "list_directory", "safe_search", "ripgrep_search"}
        )

    def _bounded_prompt_text(self, text: str, *, limit: int = 320) -> str:
        cleaned = " ".join(text.split())
        return cleaned[:limit]

    async def _memory_summary(self, principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        memory_svc = UserMemoryService(self.session)
        memories = await memory_svc.list_memories(principal, limit=12)
        if not memories:
            return "I don't have any saved memory yet."
        lines = ["What I remember about you:"]
        for memory in memories:
            lines.append(f"- {memory.key}: {memory.value_summary}")
        return "\n".join(lines)

    async def _remember_memory(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        statement = args.get("statement", "").strip()
        if not statement:
            return "Usage: remember that <fact>"
        parsed = self._parse_memory_fact(statement)
        memory_svc = UserMemoryService(self.session)
        kernel = MemoryKernelService(self.session, self.settings)
        predicate = "stored_in" if "value_summary" in parsed else "related_to"
        location_match = re.search(
            r"(?:in|at|under|inside)\s+(?P<location>.+)$",
            parsed.get("value_summary", ""),
            re.I,
        )
        if location_match:
            predicate = "stored_in"
        try:
            record = await memory_svc.remember(
                principal,
                key=parsed["key"],
                value_summary=parsed["value_summary"],
                source="user",
                confidence=0.9,
                user_editable=True,
            )
            await kernel.remember_fact(
                principal.user_id,
                subject=parsed["key"],
                predicate=predicate,
                object_summary=parsed["value_summary"],
                user_confirmed=True,
            )
        except Exception as exc:
            return f"Blocked: {exc}"
        return f"Remembered {record.key}: {record.value_summary}"

    async def _forget_memory(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        statement = args.get("statement", "").strip()
        if not statement:
            return "Usage: forget <memory key>"
        memory_svc = UserMemoryService(self.session)
        key = self._parse_memory_fact(statement).get("key", statement)
        deleted = await memory_svc.forget(principal, key)
        kernel = MemoryKernelService(self.session, self.settings)
        kernel_counts = await kernel.forget_topic(principal.user_id, key)
        if not deleted and kernel_counts["facts"] == 0 and kernel_counts["chunks"] == 0:
            return f"I don't have a saved memory for '{key}'."
        return f"Forgot {key}."

    async def _memory_lookup(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        subject = args.get("subject", "").strip()
        if not subject:
            return "I don't know that yet."
        memory_svc = UserMemoryService(self.session)
        memories = await memory_svc.list_memories(principal, limit=20)
        subject_norm = self._normalize_memory_subject(subject)
        for memory in memories:
            key_norm = self._normalize_memory_subject(memory.key)
            if subject_norm in key_norm or key_norm in subject_norm:
                return memory.value_summary
        kernel = MemoryKernelService(self.session, self.settings)
        from nova_core.memory.retrieval import format_retrieval_result

        result = await kernel.retrieve(principal.user_id, subject, limit=5)
        for hit in result.hits:
            if hit.kind == "fact" and hit.provenance == "memory_facts":
                parts = hit.summary.split(" ", 2)
                if len(parts) >= 3 and parts[1] == "stored_in":
                    return parts[2]
        if result.hits:
            return format_retrieval_result(result)
        location = args.get("location")
        if location:
            return f"{subject} is usually in {location}."
        return "I don't know that yet."

    def _memory_kernel(self) -> MemoryKernelService:
        return MemoryKernelService(self.session, self.settings)

    async def _memory_enable_broad(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        await self._memory_kernel().set_access_profile(principal.user_id, AccessProfile.BROAD_LOCAL)
        return (
            "Broad local knowledge enabled. NOVA may index your home directory "
            "(except ~/NOVA_VAULT, which remains permanently invisible)."
        )

    async def _memory_disable_broad(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        await self._memory_kernel().set_access_profile(principal.user_id, AccessProfile.MINIMAL)
        return (
            "Broad local knowledge disabled. "
            "Using minimal profile (Desktop, Documents, Downloads, Projects)."
        )

    async def _memory_status(self, principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        svc = AgentMissionService(self.session, self.settings)
        return await svc.memory_status_text(principal.user_id)

    async def _memory_index_mac(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        result = await self._memory_kernel().scan_sources(principal.user_id)
        processed = await self._memory_kernel().process_pending_jobs(principal.user_id, limit=10)
        return (
            f"Bounded local scan complete. Discovered {result.get('discovered', 0)} files; "
            f"processed {processed} deep-index jobs."
        )

    async def _memory_pause_indexing(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        await self._memory_kernel().pause_indexing(principal.user_id)
        return "Local indexing paused."

    async def _memory_resume_indexing(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        await self._memory_kernel().resume_indexing(principal.user_id)
        return "Local indexing resumed."

    async def _memory_index_progress(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        return await self._memory_status(principal, _args, **_kw)

    async def _memory_search(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        from nova_core.memory.retrieval import format_retrieval_result

        query = args.get("query", "").strip()
        if not query:
            return "Usage: search my memory for <topic>"
        result = await self._memory_kernel().retrieve(principal.user_id, query, limit=8)
        return format_retrieval_result(result)

    async def _memory_recall(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        return await self._memory_search(principal, args, **_kw)

    async def _memory_forget_topic(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        topic = args.get("topic", "").strip()
        if not topic:
            return "Usage: forget everything about <topic>"
        result = await self._memory_kernel().forget_topic(principal.user_id, topic)
        return (
            f"Forgot topic '{topic}': {result['facts']} facts, {result['chunks']} chunks removed."
        )

    async def _memory_forget_id(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        from nova_core.models.orm import MemoryFact

        memory_id = args.get("memory_id", "").strip()
        if not memory_id:
            return "Usage: forget memory <id>"
        fact = await self.session.get(MemoryFact, memory_id)
        if fact is None or fact.user_id != principal.user_id:
            return f"No memory found for id {memory_id}."
        fact.valid_until = datetime.now(tz=UTC)
        return f"Forgot memory {memory_id}."

    async def _memory_export(self, principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        import json

        data = await self._memory_kernel().export_memory(principal.user_id)
        valid = await self._memory_kernel().audit_integrity(principal.user_id)
        return (
            f"Local memory export (local-only, audit chain valid={valid}):\n"
            f"{json.dumps(data, indent=2)[:4000]}"
        )

    async def _memory_find_files(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        topic = args.get("topic", "").strip()
        if not topic:
            return "Usage: find my <topic> files"
        kernel_result = await self._memory_search(principal, {"query": topic}, **_kw)
        if "No local memory matches" not in kernel_result:
            return kernel_result
        return await self._search_computer_prompt(
            principal, {"pattern": topic.replace(" files", "").strip()}, **_kw
        )

    async def _project_history(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        project_svc = ProjectService(self.session, self.settings)
        active = await project_svc.get_active_project_or_none(principal)
        if active is None:
            return "No active project. Use set project <path> first."
        return await self._memory_kernel().format_project_history(
            principal.user_id, active.project_root
        )

    async def _project_yesterday(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        project_svc = ProjectService(self.session, self.settings)
        active = await project_svc.get_active_project_or_none(principal)
        root = active.project_root if active else None
        return await format_yesterday_summary(self.session, principal.user_id, root)

    async def _project_last_failure(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        project_svc = ProjectService(self.session, self.settings)
        active = await project_svc.get_active_project_or_none(principal)
        root = active.project_root if active else None
        return await format_last_failure(self.session, principal.user_id, root)

    async def _project_open_loops(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        project_svc = ProjectService(self.session, self.settings)
        active = await project_svc.get_active_project_or_none(principal)
        root = active.project_root if active else None
        return await format_open_loops(self.session, principal.user_id, root)

    async def _project_remember_decision(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        text = args.get("text", "").strip()
        if not text:
            return "Usage: remember this project decision: <text>"
        project_svc = ProjectService(self.session, self.settings)
        active = await project_svc.get_active_project_or_none(principal)
        if active is None:
            return "No active project."
        await remember_project_decision(
            self.session,
            principal.user_id,
            project_root=active.project_root,
            text=text,
        )
        return f"Recorded project decision: {text}"

    async def _archive_search(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        query = args.get("query", "").strip()
        if not query:
            return "Usage: search my Mac for <topic>"
        svc = AgentMissionService(self.session, self.settings)
        return await svc.archive_search(principal.user_id, query)

    async def _agent_os_mission(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        request = args.get("request", "").strip()
        if not request:
            return (
                "Usage: build a calculator app | build a todo app | build a landing page for <name>"
            )
        app_request = parse_app_request(request)
        if app_request is None:
            app_request = parse_app_request(f"build a simple web app for {request}")
        if app_request is None:
            return "Could not parse app build request."
        session_id = _kw.get("session_id")
        if app_request.requires_clarification:
            return app_request.clarification_message
        if is_vague_app_request(app_request) and session_id:
            pending_svc = PendingToolIntentService(self.session)
            await pending_svc.create_app_spec_clarification(
                principal,
                session_id=session_id,
                raw_request=request,
                app_type=app_request.app_type,
                app_name=app_request.app_name,
                runtime=app_request.runtime,
            )
            self._pending_tool_intent_type = "agent_os_app_spec"
            return build_clarification_message(app_request)
        svc = AgentMissionService(self.session, self.settings)
        mission = svc.run_mission(request, run_npm=True, clean_workspace=True, start_preview=True)
        self._store_agent_mission_payload(mission)
        return svc.mission_timeline_text(mission.mission_id)

    async def _try_resolve_pending_app_spec(
        self,
        principal: Principal,
        text: str,
        session_id: str,
        *,
        routing: Any | None = None,
    ) -> dict[str, Any] | None:
        pending_svc = PendingToolIntentService(self.session)
        record = await pending_svc.get_active(principal, session_id)
        if record is None:
            return None
        if record.intent_type != PendingToolIntentType.APP_SPEC_CLARIFICATION.value:
            return None
        payload = pending_svc.payload_app_spec(record)
        raw_request = payload["raw_request"]
        app_request = parse_app_request(raw_request)
        if app_request is None:
            await pending_svc.consume(record, status=PendingToolIntentStatus.CANCELLED)
            return self._response(
                "That app build request expired. Please start again.",
                intent="pending_expired",
                routing=routing,
                session_id=session_id,
            )
        lowered = text.lower().strip()
        if lowered in {"cancel", "stop", "never mind"}:
            await pending_svc.consume(record, status=PendingToolIntentStatus.CANCELLED)
            return self._response(
                "App build cancelled.",
                intent="pending_cancelled",
                routing=routing,
                session_id=session_id,
            )
        use_assumptions = is_assumption_continuation(text)
        if not use_assumptions and not text.strip():
            return self._response(
                build_clarification_message(app_request),
                intent="agent_os_app_spec",
                routing=routing,
                session_id=session_id,
                pending_tool_intent=record.intent_type,
            )
        enhanced, assumptions = merge_request_with_answers(
            raw_request,
            app_request,
            text,
            use_assumptions=use_assumptions,
        )
        await pending_svc.consume(record)
        intro = (
            "Great. Building with assumptions…"
            if use_assumptions
            else "Thanks — incorporating your guidance and building now…"
        )
        svc = AgentMissionService(self.session, self.settings)
        mission = svc.run_mission(
            enhanced,
            run_npm=True,
            clean_workspace=True,
            start_preview=True,
            assumptions=assumptions,
        )
        self._store_agent_mission_payload(mission)
        body = f"{intro}\n\n{svc.mission_timeline_text(mission.mission_id)}"
        extra = self._collect_handler_extra("agent_os_mission")
        return self._response(
            body,
            intent="agent_os_mission",
            routing=routing,
            session_id=session_id,
            **extra,
        )

    async def _orbit_email_draft(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        request_text = args.get("request", "").strip()
        parsed = parse_email_draft_request(request_text)
        if parsed is None:
            return "Usage: draft an investor update email about this app"
        svc = OrbitEmailService(self.settings)
        draft = svc.create_draft(parsed)
        self._last_orbit_email_meta = svc.payload_for(draft)
        payload = self._last_orbit_email_meta
        return (
            "Email draft ready.\n\n"
            f"To: {draft.to}\n"
            f"Subject: {draft.subject}\n\n"
            f"{draft.body[:800]}\n\n"
            f"Draft source: {payload['result']['draft_source']}\n"
            "Send this email?"
        )

    async def _orbit_email_send_yes(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = OrbitEmailService(self.settings)
        try:
            draft = svc.approve_send()
        except ValueError as exc:
            return str(exc)
        self._last_orbit_email_meta = svc.payload_for(draft)
        return (
            "Send approval recorded.\n"
            "Gmail send integration is prepared but not enabled in this build."
        )

    async def _orbit_email_send_no(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = OrbitEmailService(self.settings)
        try:
            draft = svc.skip_send()
        except ValueError as exc:
            return str(exc)
        self._last_orbit_email_meta = svc.payload_for(draft)
        return "Email send skipped."

    async def _orbit_email_send_blocked(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        return (
            "Blocked: sending email requires a drafted message and explicit approval. "
            "Try: draft an investor update email about this app"
        )

    async def _agent_os_deploy_yes(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = AgentMissionService(self.session, self.settings)
        mission = svc.latest_awaiting_approval()
        if mission is None:
            return "No mission is awaiting deployment approval."
        mission = svc.deploy_mission(mission.mission_id)
        self._store_agent_mission_payload(mission)
        return self._approval_recorded_message(mission)

    async def _agent_os_deploy_no(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = AgentMissionService(self.session, self.settings)
        mission = svc.latest_awaiting_approval()
        if mission is None:
            return "No mission is awaiting deployment approval."
        mission = svc.skip_deployment(mission.mission_id)
        self._store_agent_mission_payload(mission)
        return self._approval_skipped_message(mission)

    async def _agent_os_preview(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = AgentMissionService(self.session, self.settings)
        mission_id = getattr(self, "_last_agent_mission_id", None)
        mission = svc.get_mission(mission_id) if mission_id else None
        if mission is None or not mission.preview_url:
            latest = svc.runner.store.list_ids()
            for mid in reversed(latest):
                candidate = svc.get_mission(mid)
                if candidate and candidate.preview_url:
                    mission = candidate
                    break
        if mission is None or not mission.preview_url:
            return "No verified preview URL for the latest app mission."
        return f"Preview: {mission.preview_url}"

    async def _agent_os_mission_status(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        mission_id = getattr(self, "_last_agent_mission_id", None)
        if not mission_id:
            return "No recent Agent OS mission in this session."
        svc = AgentMissionService(self.session, self.settings)
        mission = svc.get_mission(mission_id)
        if mission is None:
            return f"Mission not found: {mission_id}"
        return (
            f"Mission {mission.mission_id}\n"
            f"Status: {mission.status.value}\n"
            f"Type: {mission.mission_type}\n"
            f"Build: {mission.final_report.get('build_status', 'unknown')}\n"
            f"Deployment: {mission.final_report.get('deployment_status', 'unknown')}"
        )

    async def _agent_os_timeline(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        mission_id = getattr(self, "_last_agent_mission_id", None)
        if not mission_id:
            return "No recent Agent OS mission timeline."
        svc = AgentMissionService(self.session, self.settings)
        return svc.mission_timeline_text(mission_id)

    async def _agent_os_approve_deploy(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        mission_id = getattr(self, "_last_agent_mission_id", None)
        if not mission_id:
            return "No mission awaiting deployment approval."
        svc = AgentMissionService(self.session, self.settings)
        mission = svc.approve_deployment(mission_id)
        return (
            f"Deployment approved for mission {mission.mission_id}. "
            "External deploy remains manual in v1."
        )

    async def _system_memory_status(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        import platform
        import subprocess

        if platform.system() != "Darwin":
            return "System memory status is only available on macOS in this build."
        proc = subprocess.run(["vm_stat"], capture_output=True, text=True, check=False)
        return f"System memory status (RAM):\n{proc.stdout[:1200]}"

    def _parse_memory_fact(self, statement: str) -> dict[str, str]:
        text = re.sub(r"\s+", " ", statement.strip()).rstrip(".")
        patterns = (
            r"^(?P<key>.+?)\s+(?:is|are|was|were)\s+(?:usually\s+)?(?:stored\s+)?(?:in|at|on|under|inside)\s+(?P<value>.+)$",
            r"^(?:my|the)\s+(?P<key>.+?)\s+(?:is|are)\s+(?:usually\s+)?(?:in|at|on|under|inside)\s+(?P<value>.+)$",
            (
                r"^(?P<key>.+?)\s+(?:usually\s+)?"
                r"(?:lives|lives in|resides|resides in)\s+(?P<value>.+)$"
            ),
        )
        for pattern in patterns:
            match = re.match(pattern, text, re.I)
            if match:
                key = self._normalize_memory_subject(match.group("key"))
                value = match.group("value").strip()
                return {"key": key, "value_summary": value}
        key = self._normalize_memory_subject(text)
        return {"key": key, "value_summary": text}

    def _normalize_memory_subject(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.strip()).lower()
        cleaned = cleaned.replace("my ", "").replace("the ", "")
        return cleaned[:255]

    async def _try_resolve_pending_tool_intent(
        self,
        principal: Principal,
        text: str,
        session_id: str,
        *,
        routing: Any | None = None,
    ) -> dict[str, Any] | None:
        pending_svc = PendingToolIntentService(self.session)
        parsed = parse_scope_confirmation_reply(text)
        record = await pending_svc.get_active(principal, session_id)

        if record is None:
            if parsed.action != "unrelated":
                expired = await pending_svc.get_recently_expired(principal, session_id)
                if expired is not None and expired.consumed_at is not None:
                    consumed_at = expired.consumed_at
                    if consumed_at.tzinfo is None:
                        consumed_at = consumed_at.replace(tzinfo=UTC)
                    if consumed_at >= datetime.now(UTC) - timedelta(minutes=2):
                        return self._response(
                            "That search request expired. Please start again.",
                            intent="pending_expired",
                            routing=routing,
                            session_id=session_id,
                        )
            return None

        if record.intent_type != PendingToolIntentType.PERSONAL_SEARCH_SCOPE_CONFIRMATION.value:
            return None

        query = pending_svc.payload_query(record)

        if parsed.action == "cancel":
            await pending_svc.consume(record, status=PendingToolIntentStatus.CANCELLED)
            return self._response(
                "Search cancelled.",
                intent="pending_cancelled",
                routing=routing,
                session_id=session_id,
            )

        if parsed.action == "unrelated":
            return self._response(
                unrelated_pending_message(query),
                intent="pending_scope_confirmation",
                routing=routing,
                session_id=session_id,
                pending_tool_intent=record.intent_type,
            )

        if parsed.action == "all_approved":
            await pending_svc.consume(record)
            body = await self._safe_search(
                principal,
                {"pattern": query, "scope": "all_approved"},
                routing=routing,
                session_id=session_id,
            )
            return self._finalize_pending_search_response(
                body, routing=routing, session_id=session_id
            )

        if parsed.action == "scope_path" and parsed.path:
            if is_protected_path(parsed.path):
                return self._response(
                    PROTECTED_PATH_MESSAGE,
                    intent="blocked",
                    routing=routing,
                    blocked=True,
                    session_id=session_id,
                )
            await pending_svc.consume(record)
            body = await self._safe_search(
                principal,
                {"pattern": query, "path": parsed.path, "scope": "path"},
                routing=routing,
                session_id=session_id,
            )
            return self._finalize_pending_search_response(
                body, routing=routing, session_id=session_id
            )

        return None

    def _finalize_pending_search_response(
        self,
        body: str,
        *,
        routing: Any | None,
        session_id: str,
    ) -> dict[str, Any]:
        if body.startswith("Blocked:"):
            return self._response(
                body,
                intent="blocked",
                routing=routing,
                blocked=True,
                session_id=session_id,
            )
        return self._response(
            body,
            intent="safe_search",
            routing=routing,
            session_id=session_id,
        )

    async def _system_status(self, _principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        availability = await get_worker_availability(self.session, self.settings)
        active = await self.session.execute(
            select(Mission).where(Mission.status == MissionStatus.RUNNING.value)
        )
        running = len(active.scalars().all())
        stale = availability["workers_stale"]
        offline = availability["workers_offline"]
        return (
            "System Status\n"
            "─────────────\n"
            "Control plane: healthy\n"
            f"Workers online: {availability['workers_online']}/{availability['workers_total']}\n"
            f"  stale: {stale}  offline: {offline}\n"
            f"Active missions: {running}"
        )

    async def _connected_devices(
        self, _principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = DeviceService(self.session, self.settings)
        devices = await svc.list_devices()
        if not devices:
            return "Connected Devices\n───────────────\n(no devices paired)"
        lines = [
            f"• {d.name}\n  id: {d.id}\n  type: {d.device_type}  status: {d.status}"
            for d in devices
        ]
        return "Connected Devices\n───────────────\n" + "\n\n".join(lines)

    async def _worker_status(self, _principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        availability = await get_worker_availability(self.session, self.settings)
        eligible = "yes" if availability["has_eligible_online_worker"] else "no"
        online = availability["workers_online"]
        stale = availability["workers_stale"]
        offline = availability["workers_offline"]
        revoked = availability["workers_revoked"]
        return (
            f"Workers online={online}, stale={stale}, offline={offline}, revoked={revoked}. "
            f"Eligible online worker: {eligible}."
        )

    async def _recent_missions(
        self, _principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        result = await self.session.execute(
            select(Mission).order_by(Mission.created_at.desc()).limit(10)
        )
        missions = result.scalars().all()
        if not missions:
            return "No recent missions."
        lines = [f"- {m.title} ({m.mission_type}) status={m.status}" for m in missions]
        return "Recent missions:\n" + "\n".join(lines)

    async def _create_system_status_mission(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        svc = MissionService(self.session, self.settings)
        mission = await svc.create_and_run(
            user_id=principal.user_id,
            mission_type="system_status",
            title="Chat: system status mission",
            request_payload={"source": "chat"},
            principal=principal,
        )
        return f"Created system_status mission {mission.id} with status {mission.status}."

    async def _worker_capabilities(
        self, _principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        from apps.worker.commands import execute_read_only_command

        payload = execute_read_only_command("configured_capabilities")
        caps = payload.get("capabilities", [])
        return "Worker capabilities:\n" + "\n".join(f"- {c}" for c in caps)

    async def _list_directory(
        self,
        principal: Principal,
        args: dict[str, str],
        *,
        routing: Any | None = None,
        session_id: str | None = None,
        **_kw: Any,
    ) -> str:
        path = args.get("path", ".")
        guard = await self._guard_path_access(principal, path, routing)
        if not guard.allowed:
            if guard.approval_resolution is not None:
                return await self._format_approval_message(
                    principal, guard.approval_resolution, session_id
                )
            return guard.blocked_message or BLOCKED_MESSAGE
        evaluation = self._policy.evaluate("list_directory", category="filesystem_read")
        if evaluation.decision != ToolDecision.AUTO_APPROVE:
            await self._audit_blocked(principal, sanitize_path_for_log(path), reason="policy_block")
            return BLOCKED_MESSAGE
        result = self._safe_tools.list_directory(path)
        if not result.success:
            return await self._handle_tool_error(principal, path, result.error)
        output = result.output
        assert isinstance(output, dict)
        entries = output.get("entries", [])
        lines = [f"  {'📁' if e.get('is_dir') else '📄'} {e.get('name')}" for e in entries[:30]]
        body = "\n".join(lines) if lines else "  (empty)"
        truncated = " (truncated)" if output.get("truncated") else ""
        return f"Directory: {output.get('path')}{truncated}\n{body}"

    async def _read_file(
        self,
        principal: Principal,
        args: dict[str, str],
        *,
        routing: Any | None = None,
        session_id: str | None = None,
        **_kw: Any,
    ) -> str:
        path = args.get("path", "")
        guard = await self._guard_path_access(principal, path, routing)
        if not guard.allowed:
            if guard.approval_resolution is not None:
                return await self._format_approval_message(
                    principal, guard.approval_resolution, session_id
                )
            return guard.blocked_message or BLOCKED_MESSAGE
        evaluation = self._policy.evaluate("read_file", category="filesystem_read")
        if evaluation.decision != ToolDecision.AUTO_APPROVE:
            await self._audit_blocked(principal, sanitize_path_for_log(path), reason="policy_block")
            return BLOCKED_MESSAGE
        result = self._safe_tools.read_file(path)
        if not result.success:
            return await self._handle_tool_error(principal, path, result.error)
        output = result.output
        assert isinstance(output, dict)
        content = str(output.get("content", ""))
        preview = content[:1200] + ("…" if len(content) > 1200 else "")
        return f"File: {output.get('path')}\nSize: {output.get('size')} bytes\n\n{preview}"

    async def _search_computer_prompt(
        self,
        principal: Principal,
        args: dict[str, str],
        *,
        session_id: str | None = None,
        **_kw: Any,
    ) -> str:
        pattern = args.get("pattern", "").strip()
        if not pattern:
            return "Usage: search my computer for <pattern>"
        if not session_id:
            return scope_confirmation_prompt(pattern)
        pending_svc = PendingToolIntentService(self.session)
        await pending_svc.create_scope_confirmation(
            principal,
            session_id=session_id,
            query=pattern,
        )
        self._pending_tool_intent_type = (
            PendingToolIntentType.PERSONAL_SEARCH_SCOPE_CONFIRMATION.value
        )
        return scope_confirmation_prompt(pattern)

    async def _safe_search(
        self,
        principal: Principal,
        args: dict[str, str],
        *,
        routing: Any | None = None,
        session_id: str | None = None,
        **_kw: Any,
    ) -> str:
        pattern = args.get("pattern", "").strip()
        if not pattern:
            return "Usage: search <pattern> [in ~/Downloads]"

        scope = args.get("scope", "active_project")
        evaluation = self._policy.evaluate("ripgrep_search", category="search")
        if evaluation.decision != ToolDecision.AUTO_APPROVE:
            await self._audit_blocked(principal, pattern, reason="policy_block")
            return BLOCKED_MESSAGE

        if scope == "all_approved":
            if routing is not None and is_cloud_provider(routing.provider):
                return "Blocked: cloud providers cannot receive multi-folder search results yet."
            result = self._personal_search.search_all_approved(pattern)
            if not result.success:
                return f"Blocked: {result.error}"
            assert result.output is not None
            return format_search_results(pattern, result.output)

        if scope == "active_project":
            project_svc = ProjectService(self.session, self.settings)
            active = await project_svc.get_active_project_or_none(principal)
            if active is None:
                return "No active project. Use: set project ~/Projects/nova"
            search_path = active.project_root
        else:
            search_path = args.get("path", "").strip()
            if not search_path:
                return "Usage: search <pattern> in ~/Downloads"

        if is_protected_path(search_path):
            await self._audit_blocked(
                principal,
                sanitize_path_for_log(search_path),
                reason="protected_path_block",
            )
            return PROTECTED_PATH_MESSAGE

        if routing is not None and is_cloud_provider(routing.provider):
            transmission = evaluate_file_transmission(routing.provider, search_path, approved=False)
            if transmission.decision != FileTransmissionDecision.ALLOW:
                return await self._format_approval_message(
                    principal,
                    cloud_file_resolution(search_path),
                    session_id,
                )

        if scope == "active_project":
            guard = await self._guard_path_access(principal, search_path, routing)
            if not guard.allowed:
                if guard.approval_resolution is not None:
                    return await self._format_approval_message(
                        principal, guard.approval_resolution, session_id
                    )
                return guard.blocked_message or BLOCKED_MESSAGE
            legacy = self._safe_tools.ripgrep_search(pattern, search_path)
            if not legacy.success:
                return await self._handle_tool_error(principal, search_path, legacy.error)
            output = legacy.output
            assert isinstance(output, dict)
            matches = output.get("matches", [])
            if not matches:
                return f'Found 0 matches for "{pattern}".'
            grouped: dict[str, list[dict[str, Any]]] = {}
            for match in matches:
                path_key = str(match.get("path", ""))
                grouped.setdefault(path_key, []).append(match)
            formatted = format_search_results(
                pattern,
                {
                    "match_count": len(matches),
                    "by_file": {
                        k: [{"line": m.get("line"), "text": m.get("text")} for m in v]
                        for k, v in grouped.items()
                    },
                    "truncated": output.get("truncated", False),
                },
            )
            return formatted

        scope_check = resolve_search_scope(search_path, search_roots=self._search_roots)
        if not scope_check.allowed:
            await self._audit_blocked(
                principal,
                sanitize_path_for_log(search_path),
                reason="search_scope_block",
            )
            return scope_check.reason or BLOCKED_MESSAGE

        result = self._personal_search.search_scope(pattern, search_path)
        if not result.success:
            return f"Blocked: {result.error}"
        assert result.output is not None
        return format_search_results(pattern, result.output)

    async def _repo_analysis(
        self,
        principal: Principal,
        args: dict[str, str],
        *,
        routing: Any | None = None,
        session_id: str | None = None,
        **_kw: Any,
    ) -> str:
        path = args.get("path", "~/Projects/nova")
        guard = await self._guard_path_access(principal, path, routing)
        if not guard.allowed:
            if guard.approval_resolution is not None:
                return await self._format_approval_message(
                    principal, guard.approval_resolution, session_id
                )
            return guard.blocked_message or BLOCKED_MESSAGE
        result = self._code_runtime.repo_analysis(path)
        if not result.success:
            return await self._handle_tool_error(principal, path, result.error)
        signals = result.output["signals"]
        return (
            f"Repo Analysis: {result.output['repo']}\n"
            f"  Python: {'yes' if signals['python'] else 'no'}\n"
            f"  iOS: {'yes' if signals['ios'] else 'no'}\n"
            f"  Docs: {'yes' if signals['docs'] else 'no'}\n"
            f"  Tests: {'yes' if signals['tests'] else 'no'}"
        )

    async def _explain_code(
        self,
        principal: Principal,
        args: dict[str, str],
        *,
        routing: Any | None = None,
        session_id: str | None = None,
        **_kw: Any,
    ) -> str:
        path = args.get("path", "")
        guard = await self._guard_path_access(principal, path, routing)
        if not guard.allowed:
            if guard.approval_resolution is not None:
                return await self._format_approval_message(
                    principal, guard.approval_resolution, session_id
                )
            return guard.blocked_message or BLOCKED_MESSAGE
        result = self._code_runtime.explain_code(path)
        if not result.success:
            return await self._handle_tool_error(principal, path, result.error)
        return (
            f"Code: {result.output['path']}\n"
            f"Lines: {result.output['line_count']}\n\n"
            f"{result.output['summary']}"
        )

    async def _patch_plan(
        self,
        principal: Principal,
        args: dict[str, str],
        *,
        session_id: str | None = None,
        **_kw: Any,
    ) -> str:
        instruction = args.get("instruction", "")
        result = self._code_runtime.patch_plan(instruction)
        plan = "; ".join(result.output["plan"])
        resolution = ActionResolution(
            capability=CapabilityName.CODE_PATCH,
            payload={"instruction": instruction, "plan": result.output["plan"]},
            action_summary=f"Generate code patch: {instruction[:120]}",
            preview=plan[:500] or instruction[:500],
            risk_level=risk_for_capability(CapabilityName.CODE_PATCH),
        )
        return await self._format_approval_message(principal, resolution, session_id)

    async def _set_project(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        path = args.get("path", "").strip()
        if not path:
            return "Usage: set project ~/Projects/nova"
        svc = ProjectService(self.session, self.settings)
        try:
            record = await svc.set_active_project(principal, path)
        except Exception as exc:
            return f"Blocked: {exc}"
        self._pending_active_project = record.project_name
        tooling = ", ".join(k for k, v in (record.detected_tooling or {}).items() if v)
        return (
            f"Active project set.\n"
            f"Name: {record.project_name}\n"
            f"Root: {record.project_root}\n"
            f"Branch: {record.current_branch or '(unknown)'}\n"
            f"Tooling: {tooling or 'none'}"
        )

    async def _current_project(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = ProjectService(self.session, self.settings)
        try:
            record = await svc.get_active_project(principal)
        except Exception:
            return "No active project. Use: set project ~/Projects/nova"
        return (
            f"Active project: {record.project_name}\n"
            f"Root: {record.project_root}\n"
            f"Branch: {record.current_branch or '(unknown)'}\n"
            f"Last opened: {record.last_opened_at.isoformat()}"
        )

    async def _inspect_repo(self, principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        svc = ProjectService(self.session, self.settings)
        try:
            record = await svc.get_active_project(principal)
        except Exception:
            return "No active project. Use: set project ~/Projects/nova"
        from pathlib import Path

        inspection = await inspect_repo(Path(record.project_root))
        record.current_branch = inspection.current_branch
        return format_inspection(inspection)

    async def _summarize_repo(self, principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        svc = ProjectService(self.session, self.settings)
        try:
            record = await svc.get_active_project(principal)
        except Exception:
            return "No active project. Use: set project ~/Projects/nova"
        from pathlib import Path

        inspection = await inspect_repo(Path(record.project_root))
        cmds = ", ".join(f"{k}={v}" for k, v in inspection.detected_commands.items()) or "none"
        return (
            f"{inspection.project_name} @ {inspection.current_branch}\n"
            f"Root: {inspection.project_root}\n"
            f"Validation: {cmds}\n"
            f"Status: {inspection.git_status[:300]}"
        )

    async def _background_tasks(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = BackgroundTaskService(self.session, self.settings)
        tasks = await svc.list_tasks(principal)
        if not tasks:
            return "Background Tasks\n──────────────\n(no tasks scheduled)"
        lines = []
        for task in tasks:
            nxt = task.next_run_at.isoformat() if task.next_run_at else "—"
            lines.append(
                f"• {task.title}\n"
                f"  id: {task.id}\n"
                f"  type: {task.task_type}  status: {task.status}\n"
                f"  schedule: {task.schedule_kind} {task.schedule_expression}\n"
                f"  next: {nxt}"
            )
        return "Background Tasks\n──────────────\n" + "\n\n".join(lines)

    async def _create_background_task(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        svc = BackgroundTaskService(self.session, self.settings)
        project_svc = ProjectService(self.session, self.settings)
        active = await project_svc.get_active_project_or_none(principal)
        if active is None and args.get("task_type") not in {
            BackgroundTaskType.SYSTEM_STATUS.value,
            BackgroundTaskType.REMINDER_NOTE.value,
        }:
            return "No active project. Use: set project <path> first."
        title = args.get("title") or BackgroundTaskService.default_title_for_type(args["task_type"])
        task = await svc.create_task(
            principal,
            task_type=args["task_type"],
            title=title,
            prompt=None,
            project_root=active.project_root if active else None,
            schedule_kind=args["schedule_kind"],
            schedule_expression=args["schedule_expression"],
        )
        await self.session.flush()
        nxt = task.next_run_at.isoformat() if task.next_run_at else "—"
        return (
            f"Created background task {task.id}\n"
            f"Title: {task.title}\n"
            f"Type: {task.task_type}\n"
            f"Schedule: {task.schedule_kind} {task.schedule_expression}\n"
            f"Next run: {nxt}\n"
            f"Status: {task.status}"
        )

    async def _pause_background_task(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        task_id = args.get("task_id", "").strip()
        if not task_id:
            return "Usage: pause task <id>"
        svc = BackgroundTaskService(self.session, self.settings)
        task = await svc.pause_task(principal, task_id)
        await self.session.flush()
        return f"Paused task {task.id} ({task.title})"

    async def _resume_background_task(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        task_id = args.get("task_id", "").strip()
        if not task_id:
            return "Usage: resume task <id>"
        svc = BackgroundTaskService(self.session, self.settings)
        task = await svc.resume_task(principal, task_id)
        await self.session.flush()
        nxt = task.next_run_at.isoformat() if task.next_run_at else "—"
        return f"Resumed task {task.id}. Next run: {nxt}"

    async def _cancel_background_task(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        task_id = args.get("task_id", "").strip()
        if not task_id:
            return "Usage: cancel task <id>"
        svc = BackgroundTaskService(self.session, self.settings)
        task = await svc.cancel_task(principal, task_id)
        await self.session.flush()
        return f"Cancelled task {task.id} ({task.title})"

    async def _run_background_task(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        task_id = args.get("task_id", "").strip()
        if not task_id:
            return "Usage: run task <id> now"
        sched = BackgroundSchedulerService(self.session, self.settings)
        run = await sched.run_task_now(principal, task_id)
        await self.session.flush()
        return (
            f"Ran task {task_id} now\n"
            f"Run id: {run.id}\n"
            f"Status: {run.status}\n"
            f"Summary: {run.summary or '(none)'}"
        )

    async def _notifications_list(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = NotificationService(self.session)
        items, unread = await svc.list_notifications(principal, limit=20)
        if not items:
            return "Notifications\n─────────────\n(empty)"
        lines = []
        for item in items:
            flag = "read" if item.read_at else "unread"
            lines.append(
                f"• [{flag}] {item.title}\n  {item.summary[:200]}\n  {item.created_at.isoformat()}"
            )
        return f"Notifications ({unread} unread)\n─────────────\n" + "\n\n".join(lines)

    async def _failed_background_tasks(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = BackgroundTaskService(self.session, self.settings)
        tasks = await svc.list_tasks(principal)
        failed = [t for t in tasks if t.status == "failed" or (t.failure_count or 0) > 0]
        if not failed:
            return "No failed background tasks."
        lines = [
            f"- {t.title} ({t.id}) failures={t.failure_count} last={t.last_result_summary or '—'}"
            for t in failed
        ]
        return "Failed background tasks:\n" + "\n".join(lines)

    async def _summarize_latest_run(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = BackgroundTaskService(self.session, self.settings)
        tasks = await svc.list_tasks(principal)
        if not tasks:
            return "No background tasks."
        latest_task = tasks[0]
        runs = await svc.list_runs(principal, latest_task.id)
        if not runs:
            return f"No runs yet for task {latest_task.title} ({latest_task.id})."
        run = runs[0]
        return (
            f"Latest run for {latest_task.title}\n"
            f"Run: {run.id} status={run.status}\n"
            f"Summary: {run.summary or '(none)'}\n"
            f"Error: {run.error or '(none)'}"
        )

    async def _run_validation(self, principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        svc = ProjectService(self.session, self.settings)
        try:
            record = await svc.get_active_project(principal)
        except Exception:
            return "No active project. Use: set project ~/Projects/nova"
        from pathlib import Path

        root = Path(record.project_root)
        cmd = pick_validation_command(root) or "make test"
        safe_cfg = self._policies.get("safe_filesystem")
        allowed_roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None
        result = await run_validation_command(root, cmd, allowed_roots=allowed_roots)
        await svc.upsert_memory(
            principal,
            record.project_root,
            last_validation_command=cmd,
            last_validation_result={
                "exit_code": result.exit_code,
                "stdout": result.stdout_excerpt[:2000],
                "stderr": result.stderr_excerpt[:2000],
            },
        )
        if result.blocked:
            return f"Blocked: {result.block_reason}"
        return (
            f"Validation: {cmd}\n"
            f"Exit code: {result.exit_code}\n\n"
            f"stdout:\n{result.stdout_excerpt[:1500]}\n\n"
            f"stderr:\n{result.stderr_excerpt[:800]}"
        )

    async def _coding_task(
        self,
        principal: Principal,
        args: dict[str, str],
        *,
        session_id: str | None = None,
        **_kw: Any,
    ) -> str:
        request_text = args.get("request", "").strip()
        svc = CodingTaskService(self.session, self.settings)
        try:
            result = await svc.run_workflow(principal, request_text)
        except Exception as exc:
            return f"Blocked: {exc}"
        self._last_task_meta = {
            "task_id": result.get("task_id"),
            "timeline": result.get("timeline"),
            "approval_id": result.get("approval_id"),
            "unified_diff": result.get("unified_diff"),
            "patch_preview": result.get("patch_preview"),
        }
        project_svc = ProjectService(self.session, self.settings)
        active = await project_svc.get_active_project_or_none(principal)
        if active:
            self._last_task_meta["active_project"] = active.project_name
        if result.get("approval_id"):
            return (
                "I can do this after approval.\n\n"
                f"{result.get('message', '')}\n\n"
                f"Approval ID: {result['approval_id']}\n"
                "Open Settings → Approvals to approve, then Apply Approved Patch."
            )
        return str(result.get("message") or result.get("summary") or "Coding task finished.")

    async def _orchestration_plan(
        self,
        principal: Principal,
        args: dict[str, str],
        *,
        session_id: str | None = None,
        **_kw: Any,
    ) -> str:
        _ = session_id
        objective = args.get("objective", "Fix failing tests").strip()
        svc = AgentPlanService(self.session, self.settings)
        try:
            plan = await svc.create_plan(principal, objective=objective)
            steps = await svc._load_steps(plan.id)
            result = svc._plan_response(plan, steps)
        except Exception as exc:
            return f"Blocked: {exc}"
        self._last_task_meta = {
            "plan_id": result.get("plan_id"),
            "approval_id": result.get("approval_id"),
            "timeline": result.get("steps"),
        }
        if result.get("waiting_approval") and result.get("approval_id"):
            return (
                "I can do this after approval.\n\n"
                f"Plan {result['plan_id']} — {result.get('status')}\n"
                f"Reviewer: {result.get('reviewer_verdict', 'pending')}\n"
                f"Approval ID: {result['approval_id']}\n"
                "Approve patch, then Apply Approved Patch explicitly."
            )
        lines = [
            f"Agent plan {result['plan_id']}",
            f"Status: {result.get('status')}",
            f"Lane: {result.get('provider_lane')}",
            f"Steps: {len(result.get('steps', []))}",
        ]
        if result.get("summary"):
            lines.append(str(result["summary"])[:1500])
        return "\n".join(lines)

    async def _show_active_plan(
        self, principal: Principal, _args: dict[str, str], **_kw: Any
    ) -> str:
        svc = AgentPlanService(self.session, self.settings)
        plan = await svc.get_active_plan(principal)
        if plan is None:
            return "No active agent plan."
        steps = await svc._load_steps(plan.id)
        result = svc._plan_response(plan, steps)
        lines = [
            f"Plan: {plan.title} ({plan.id})",
            f"Status: {plan.status}  Lane: {plan.provider_lane}",
            f"Step {plan.current_step_index}/{plan.max_steps}",
            "",
            "Timeline:",
        ]
        for step in result.get("steps", []):
            lines.append(
                f"  [{step['step_index']}] {step['agent_role']} — "
                f"{step['action_type']} — {step['status']}"
            )
        return "\n".join(lines)

    async def _cancel_plan(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        svc = AgentPlanService(self.session, self.settings)
        plan_id = args.get("plan_id", "").strip()
        if not plan_id:
            active = await svc.get_active_plan(principal)
            if active is None:
                return "No active plan to cancel."
            plan_id = active.id
        plan = await svc.cancel_plan(principal, plan_id)
        return f"Plan {plan.id} cancelled."

    async def _retry_plan_step(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        svc = AgentPlanService(self.session, self.settings)
        active = await svc.get_active_plan(principal)
        if active is None:
            return "No active plan."
        step_index = int(args.get("step_index", "0"))
        result = await svc.retry_step(principal, active.id, step_index)
        return f"Retry step {step_index}: plan status {result.get('status')}"

    async def _provider_lane(self, _principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        svc = AgentPlanService(self.session, self.settings)
        info = svc.provider_lane_info()
        lines = [
            f"Active lane: {info.get('active_lane')}",
            f"Local active: {info.get('local_active')}",
            f"External enabled: {info.get('external_providers_enabled')}",
            "",
            "Providers (configured / enabled only — no keys shown):",
        ]
        for p in info.get("providers", []):
            lines.append(f"  • {p['kind']}: configured={p['configured']} enabled={p['enabled']}")
        return "\n".join(lines)

    async def _external_provider_request(
        self, principal: Principal, args: dict[str, str], **_kw: Any
    ) -> str:
        _ = principal, args
        if not self.settings.nova_external_providers_enabled:
            return (
                "External providers are disabled. "
                "Set NOVA_EXTERNAL_PROVIDERS_ENABLED=true and enable a specific provider. "
                "File transmission requires cloud.send_file approval."
            )
        return "External provider request noted — approval and feature flag required per call."

    async def _propose_commit(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        message = args.get("message", "").strip() or "fix: orchestration changes"
        project_svc = ProjectService(self.session, self.settings)
        active = await project_svc.get_active_project(principal)
        meta = self._last_task_meta or {}
        paths = meta.get("applied_files") or []
        if not paths:
            plan_svc = AgentPlanService(self.session, self.settings)
            plan = await plan_svc.get_active_plan(principal)
            if plan:
                ctx = (plan.metadata_json or {}).get("context") or {}
                proposal = ctx.get("commit_proposal") or {}
                paths = proposal.get("staged_paths") or []
        if not paths:
            return "No staged paths — apply a patch first or specify files."
        git_svc = GitWorkflowService(self.session, self.settings)
        result = await git_svc.propose_commit(
            principal,
            project_root=active.project_root,
            commit_message=message,
            staged_paths=paths,
        )
        return (
            f"Commit proposal created.\nApproval ID: {result['approval_id']}\n"
            f"Push: DISABLED\nApprove commit separately, then Commit Locally."
        )

    async def _create_branch(self, principal: Principal, args: dict[str, str], **_kw: Any) -> str:
        branch = args.get("branch_name", "").strip() or "nova/fix"
        project_svc = ProjectService(self.session, self.settings)
        active = await project_svc.get_active_project(principal)
        git_svc = GitWorkflowService(self.session, self.settings)
        result = await git_svc.propose_branch(
            principal, project_root=active.project_root, branch_name=branch
        )
        return (
            f"Branch proposal: {result['branch_name']}\n"
            f"Approval ID: {result['approval_id']}\nPush: DISABLED"
        )

    async def _commit_changes(self, principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        return (
            "Use Settings → Approvals to approve a git.commit request, "
            "then POST /api/v1/git/commit with the approval_id. Push remains blocked."
        )

    async def _task_history(self, principal: Principal, _args: dict[str, str], **_kw: Any) -> str:
        project_svc = ProjectService(self.session, self.settings)
        active = await project_svc.get_active_project_or_none(principal)
        if active is None:
            return "No active project."
        memory = await project_svc.get_memory(principal, active.project_root)
        history = (memory.recent_task_history if memory else None) or []
        if not history:
            return "No task history for this project."
        lines = ["Recent task history:"]
        for entry in history[-10:]:
            lines.append(f"  • {entry}")
        return "\n".join(lines)

    async def _guard_path_access(
        self,
        principal: Principal,
        path: str,
        routing: Any | None = None,
    ) -> PathGuardResult:
        if is_protected_path(path):
            await self._audit_blocked(
                principal,
                sanitize_path_for_log(path),
                reason="protected_path_block",
            )
            return PathGuardResult(allowed=False, blocked_message=PROTECTED_PATH_MESSAGE)
        if routing is not None and is_cloud_provider(routing.provider):
            evaluation = evaluate_file_transmission(routing.provider, path, approved=False)
            if evaluation.decision != FileTransmissionDecision.ALLOW:
                return PathGuardResult(
                    allowed=False,
                    approval_resolution=cloud_file_resolution(path),
                )
        return PathGuardResult(allowed=True)

    async def _handle_tool_error(
        self,
        principal: Principal,
        path: str,
        error: str | None,
    ) -> str:
        if not error:
            return BLOCKED_MESSAGE
        if error == PROTECTED_PATH_MESSAGE or is_protected_path(path):
            await self._audit_blocked(
                principal,
                sanitize_path_for_log(path),
                reason="protected_path_block",
            )
            return PROTECTED_PATH_MESSAGE
        if self._is_safe_tool_policy_error(error):
            await self._audit_blocked(
                principal,
                sanitize_path_for_log(path),
                reason="safe_path_block",
            )
            return BLOCKED_MESSAGE
        return f"Error: {error}"

    def _is_safe_tool_policy_error(self, error: str | None) -> bool:
        if not error:
            return False
        if error == PROTECTED_PATH_MESSAGE:
            return True
        return error.startswith(("Blocked path segment:", "Path not in allowlist:"))

    def _shell_command_preview(self, message: str) -> str:
        lowered = message.lower()
        for prefix in ("run shell ", "execute command ", "run "):
            if lowered.startswith(prefix):
                return message[len(prefix) :].strip() or message.strip()
        return message.strip()

    async def _evaluate_capability_action(
        self,
        text: str,
        principal: Principal,
        session_id: str | None,
    ) -> dict[str, Any] | None:
        resolution = resolve_chat_message(text)
        if resolution is None:
            return None

        if resolution.kind == "protected":
            await self._audit_blocked(
                principal,
                sanitize_path_for_log(resolution.preview or text),
                reason="protected_path_block",
            )
            response = self._blocked_response(
                session_id=session_id,
                extra=f" {resolution.message}",
            )
            return response

        if resolution.kind == "blocked" or (
            resolution.capability in PERMANENTLY_BLOCKED_CAPABILITIES
        ):
            await self._audit_blocked(
                principal,
                text[:120],
                reason="capability_blocked",
            )
            return self._blocked_response(
                session_id=session_id,
                extra=f" {resolution.message or BLOCKED_MESSAGE}",
            )

        if resolution.capability not in APPROVAL_REQUIRED_CAPABILITIES:
            return None

        return await self._approval_response_from_resolution(principal, resolution, session_id)

    async def _approval_response_from_resolution(
        self,
        principal: Principal,
        resolution: ActionResolution,
        session_id: str | None,
    ) -> dict[str, Any]:
        assert resolution.capability is not None
        approval = await self._approval_svc.create_request(
            principal,
            capability=resolution.capability,
            action_summary=resolution.action_summary,
            preview=resolution.preview,
            payload=resolution.payload,
            risk_level=resolution.risk_level,
            session_id=session_id,
        )
        body = self._approval_message_body(approval)
        return self._response(
            body,
            intent="approval_required",
            blocked=False,
            session_id=session_id,
            approval_required=True,
            approval_id=approval.id,
            risk_level=approval.risk_level,
        )

    async def _format_approval_message(
        self,
        principal: Principal,
        resolution: ActionResolution,
        session_id: str | None,
    ) -> str:
        response = await self._approval_response_from_resolution(principal, resolution, session_id)
        return str(response["response"])

    def _approval_message_body(self, approval: Any) -> str:
        preview = approval.command_or_payload_preview
        if approval.capability == CapabilityName.SHELL_EXECUTE.value:
            preview_line = f"Command: `{preview}`"
        elif approval.capability == CapabilityName.CODE_PATCH.value:
            preview_line = f"Patch summary: {preview[:400]}"
        else:
            preview_line = f"Preview: {preview[:400]}"
        return (
            "I can do this after approval.\n\n"
            f"Summary: {approval.action_summary}\n"
            f"Risk: {approval.risk_level}\n"
            f"{preview_line}\n\n"
            f"Approval ID: {approval.id}\n"
            "Open Settings → Approvals to approve or reject."
        )

    def _extract_approval_id(self, body: str) -> str | None:
        match = re.search(r"Approval ID: ([0-9a-f-]{36})", body)
        return match.group(1) if match else None

    async def _audit_blocked(self, principal: Principal, message: str, *, reason: str) -> None:
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action="chat.action_blocked",
            resource_type="chat",
            resource_id=None,
            details={"reason": reason, "message_preview": scrub_runtime_detail(message[:120])},
        )
        await self.session.commit()

    async def _maybe_audit_command(
        self,
        principal: Principal,
        intent: str,
        args: dict[str, str],
        body: str,
    ) -> None:
        if intent not in {
            "create_system_status_mission",
            "list_directory",
            "read_file",
            "ripgrep_search",
            "safe_search",
        }:
            return
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action=f"chat.{intent}",
            resource_type="chat",
            resource_id=intent,
            details={"args": args, "response_preview": scrub_runtime_detail(body[:200])},
        )
        await self.session.commit()

    async def _persist_assistant(
        self,
        sessions: ChatSessionService,
        chat_session: Any,
        response: dict[str, Any],
    ) -> None:
        await sessions.append_message(
            chat_session,
            role="assistant",
            content=str(response["response"]),
            intent=str(response.get("intent", "general")),
            blocked=bool(response.get("blocked", False)),
            routing=response.get("routing"),
            token_usage=response.get("token_usage"),
        )
        await self.session.commit()

    def _title(self, text: str) -> str:
        title = text.strip().splitlines()[0][:80]
        return title or "NOVA Chat"

    def _blocked_response(
        self, *, session_id: str | None = None, extra: str | None = None
    ) -> dict[str, Any]:
        message = BLOCKED_MESSAGE
        if extra:
            message = f"{BLOCKED_MESSAGE}{extra}"
        return {
            "response": message,
            "intent": "blocked",
            "blocked": True,
            "session_id": session_id,
        }

    def _response(
        self,
        body: str,
        *,
        intent: str,
        routing: Any | None = None,
        blocked: bool = False,
        session_id: str | None = None,
        token_usage: dict[str, Any] | None = None,
        approval_required: bool = False,
        approval_id: str | None = None,
        risk_level: str | None = None,
        task_id: str | None = None,
        timeline: list[dict[str, Any]] | None = None,
        unified_diff: str | None = None,
        patch_preview: str | None = None,
        active_project: str | None = None,
        pending_tool_intent: str | None = None,
        runtime_mode: str | None = None,
        selected_provider: str | None = None,
        selected_model: str | None = None,
        fallback_reason: str | None = None,
        local_available: bool | None = None,
        agent_os_mission: dict[str, Any] | None = None,
        orbit_email_draft: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "response": body,
            "intent": intent,
            "blocked": blocked,
            "session_id": session_id,
            "approval_required": approval_required,
            "approval_id": approval_id,
            "risk_level": risk_level,
        }
        if task_id:
            payload["task_id"] = task_id
        if timeline:
            payload["timeline"] = timeline
        if unified_diff:
            payload["unified_diff"] = unified_diff
        if patch_preview:
            payload["patch_preview"] = patch_preview
        if active_project:
            payload["active_project"] = active_project
        if pending_tool_intent:
            payload["pending_tool_intent"] = pending_tool_intent
        if agent_os_mission:
            payload["agent_os_mission"] = agent_os_mission
        if orbit_email_draft:
            payload["orbit_email_draft"] = orbit_email_draft
        if token_usage is not None:
            payload["token_usage"] = token_usage
        if routing is not None:
            payload["routing"] = {
                "provider": routing.provider.value,
                "mode": routing.mode,
                "paid_call_allowed": routing.paid_call_allowed,
            }
        if runtime_mode is not None:
            payload["runtime_mode"] = runtime_mode
        if selected_provider is not None:
            payload["selected_provider"] = selected_provider
        if selected_model is not None:
            payload["selected_model"] = selected_model
        if fallback_reason is not None:
            payload["fallback_reason"] = fallback_reason
        if local_available is not None:
            payload["local_available"] = local_available
        return payload
