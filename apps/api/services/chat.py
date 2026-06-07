"""Chat command routing and safe tool orchestration."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.approvals import ApprovalRequestService
from apps.api.services.background_scheduler import BackgroundSchedulerService
from apps.api.services.background_tasks import BackgroundTaskService
from apps.api.services.coding_tasks import CodingTaskService
from apps.api.services.devices import DeviceService
from apps.api.services.missions import MissionService
from apps.api.services.notifications import NotificationService
from apps.api.services.projects import ProjectService
from apps.api.services.runtime import ChatSessionService, RuntimeTelemetryService
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
from nova_core.models.enums import BackgroundScheduleKind, BackgroundTaskType, MissionStatus
from nova_core.models.orm import Mission
from nova_core.project.inspect import format_inspection, inspect_repo
from nova_core.project.validation import pick_validation_command, run_validation_command
from nova_core.providers.router import ProviderConfig, ProviderRouter
from nova_core.providers.runtime import InferenceRequest, ProviderRuntime, token_usage_dict
from nova_core.providers.stream_context import StreamCancelToken
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
from nova_core.tools.code_runtime import CodeRuntime
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
)
from nova_core.tools.safe_readonly import SafeReadonlyTools

HELP_TEXT = """NOVA commands:
- set project <path> — set active coding project
- current project — show active project
- inspect repo — inspect active project
- summarize repo — short project summary
- run validation — run safe test/lint command
- fix failing tests — inspect, validate, propose patch (approval required)
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
- search <pattern> [path] — ripgrep-style search in allowlisted paths
- help — this message

Patch apply requires separate approval + Apply Approved Patch action.
Background tasks never auto-apply patches. Protected paths always blocked."""


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
        self._safe_tools = SafeReadonlyTools(allowed_roots=roots)
        self._code_runtime = CodeRuntime(allowed_roots=roots)
        self._router = ProviderRouter(ProviderConfig())
        self._provider_runtime = ProviderRuntime(settings)
        self._approval_svc = ApprovalRequestService(session, settings)
        self._last_task_meta: dict[str, Any] | None = None

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

        intent, args = self._parse_intent(text)
        routing = self._router.route(text, intent=intent)

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

        handler = {
            "system_status": self._system_status,
            "devices": self._connected_devices,
            "worker_status": self._worker_status,
            "recent_missions": self._recent_missions,
            "create_system_status_mission": self._create_system_status_mission,
            "capabilities": self._worker_capabilities,
            "list_directory": self._list_directory,
            "read_file": self._read_file,
            "ripgrep_search": self._ripgrep_search,
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
        }.get(intent)

        if handler:
            body = await cast(Callable[..., Awaitable[str]], handler)(
                principal, args, routing=routing, session_id=chat_session.id
            )
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
            extra: dict[str, Any] = {}
            if intent == "coding_task" and self._last_task_meta:
                extra = {
                    k: self._last_task_meta.get(k)
                    for k in (
                        "task_id",
                        "timeline",
                        "approval_id",
                        "unified_diff",
                        "patch_preview",
                        "active_project",
                    )
                    if self._last_task_meta.get(k) is not None
                }
                self._last_task_meta = None
            response = self._response(
                body,
                intent=intent,
                routing=routing,
                session_id=chat_session.id,
                **extra,
            )
            await self._persist_assistant(sessions, chat_session, response)
            return response

        inference = await self._provider_runtime.infer(
            InferenceRequest(prompt=text, intent=intent, stream=stream)
        )
        await RuntimeTelemetryService(self.session).record_model_usage(inference)
        usage = token_usage_dict(inference)
        response = self._response(
            inference.content,
            intent="general",
            routing=routing,
            session_id=chat_session.id,
            token_usage=usage,
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

        intent, args = self._parse_intent(text)
        routing = self._router.route(text, intent=intent)

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

        handler = {
            "system_status": self._system_status,
            "devices": self._connected_devices,
            "worker_status": self._worker_status,
            "recent_missions": self._recent_missions,
            "create_system_status_mission": self._create_system_status_mission,
            "capabilities": self._worker_capabilities,
            "list_directory": self._list_directory,
            "read_file": self._read_file,
            "ripgrep_search": self._ripgrep_search,
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
        }.get(intent)

        if handler:
            body = await cast(Callable[..., Awaitable[str]], handler)(
                principal, args, routing=routing, session_id=chat_session.id
            )
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
                response = self._response(
                    body,
                    intent=intent,
                    routing=routing,
                    session_id=chat_session.id,
                )
            async for event in self._emit_full_response(sessions, chat_session, response):
                if cancel and cancel.cancelled:
                    yield {"event": "cancelled", "data": {}}
                    return
                yield event
            return

        content_parts: list[str] = []
        inference_request = InferenceRequest(prompt=text, intent=intent, stream=True)
        async for chunk in self._provider_runtime.stream(inference_request, cancel=cancel):
            if cancel and cancel.cancelled:
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
            "provider": "local",
            "model": "streamed",
            "input_tokens": self._provider_runtime._estimate_tokens(text),
            "output_tokens": self._provider_runtime._estimate_tokens(content),
            "mode": "stream",
            "fallback_used": False,
            "error": None,
        }
        response = self._response(
            content,
            intent="general",
            routing=routing,
            session_id=chat_session.id,
            token_usage=usage,
        )
        await self._persist_assistant(sessions, chat_session, response)
        yield {
            "event": "done",
            "data": {
                "intent": response["intent"],
                "blocked": response["blocked"],
                "session_id": chat_session.id,
                "token_usage": usage,
                "routing": response.get("routing"),
            },
        }

    async def _emit_full_response(
        self,
        sessions: ChatSessionService,
        chat_session: Any,
        response: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        body = str(response["response"])
        chunk_size = 24
        for index in range(0, len(body), chunk_size):
            yield {"event": "token", "data": {"delta": body[index : index + chunk_size]}}
            await asyncio.sleep(0.005)
        await self._persist_assistant(sessions, chat_session, response)
        yield {
            "event": "done",
            "data": {
                "intent": response.get("intent", "general"),
                "blocked": bool(response.get("blocked", False)),
                "session_id": response.get("session_id"),
                "token_usage": response.get("token_usage"),
                "routing": response.get("routing"),
            },
        }

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

        if lowered.startswith("search "):
            remainder = text[7:].strip()
            parts = remainder.split(" in ", maxsplit=1)
            pattern = parts[0].strip()
            path = parts[1].strip() if len(parts) > 1 else "."
            return "ripgrep_search", {"pattern": pattern, "path": path}

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
            "propose patch",
            "analyze this repo",
            "explain this error",
            "explain error",
        )
        if any(lowered.startswith(t) or t in lowered for t in coding_triggers):
            return "coding_task", {"request": text}

        if re.search(
            r"\b(execute|delete|write file|send email|open browser|n8n)\b",
            lowered,
        ):
            return "blocked", {}

        if re.search(r"\brun\b", lowered) and lowered not in {
            "run system status",
            "run system_status",
        }:
            return "blocked", {}

        return "general", {}

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

    async def _ripgrep_search(
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
        evaluation = self._policy.evaluate("ripgrep_search", category="search")
        if evaluation.decision != ToolDecision.AUTO_APPROVE:
            await self._audit_blocked(principal, args.get("pattern", ""), reason="policy_block")
            return BLOCKED_MESSAGE
        result = self._safe_tools.ripgrep_search(
            args.get("pattern", ""),
            args.get("path", "."),
        )
        if not result.success:
            return await self._handle_tool_error(
                principal,
                f"{args.get('pattern', '')} {path}".strip(),
                result.error,
            )
        output = result.output
        assert isinstance(output, dict)
        matches = output.get("matches", [])
        if not matches:
            return f"No matches for pattern `{output.get('pattern')}`."
        lines = [f"{m.get('path')}:{m.get('line')}: {m.get('text')}" for m in matches[:10]]
        suffix = " (truncated)" if output.get("truncated") else ""
        return f"Matches{suffix}:\n" + "\n".join(lines)

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
            details={"reason": reason, "message_preview": message[:120]},
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
        }:
            return
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action=f"chat.{intent}",
            resource_type="chat",
            resource_id=intent,
            details={"args": args, "response_preview": body[:200]},
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
        if token_usage is not None:
            payload["token_usage"] = token_usage
        if routing is not None:
            payload["routing"] = {
                "provider": routing.provider.value,
                "mode": routing.mode,
                "paid_call_allowed": routing.paid_call_allowed,
            }
        return payload
