"""Chat command routing and safe tool orchestration."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.devices import DeviceService
from apps.api.services.missions import MissionService
from apps.api.services.runtime import ChatSessionService, RuntimeTelemetryService
from nova_core.auth.principal import Principal
from nova_core.devices.availability import get_worker_availability
from nova_core.models.enums import MissionStatus
from nova_core.models.orm import Mission
from nova_core.providers.router import ProviderConfig, ProviderRouter
from nova_core.providers.runtime import InferenceRequest, ProviderRuntime, token_usage_dict
from nova_core.providers.stream_context import StreamCancelToken
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
from nova_core.tools.code_runtime import CodeRuntime
from nova_core.tools.policy import BLOCKED_MESSAGE, ToolDecision, ToolPolicy
from nova_core.tools.safe_readonly import SafeReadonlyTools

HELP_TEXT = """NOVA Phase 3A commands:
- system status — control plane and worker summary
- connected devices — paired devices list
- worker status — worker online/stale/offline counts
- recent missions — last missions
- create system status mission — queue a system_status mission
- list worker capabilities — worker capability report
- list directory [path] — read-only allowlisted directory listing
- read file <path> — read allowlisted file (max 64KB)
- search <pattern> [path] — ripgrep-style search in allowlisted paths
- help — this message

Unsafe write/shell/browser/email/automation requests are blocked."""


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

        if self._policy.is_unsafe_request_text(text):
            await self._audit_blocked(principal, text, reason="unsafe_keyword")
            response = self._blocked_response(session_id=chat_session.id)
            await sessions.append_message(
                chat_session,
                role="assistant",
                content=response["response"],
                intent="blocked",
                blocked=True,
            )
            await self.session.commit()
            return response

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
        }.get(intent)

        if handler:
            body = await handler(principal, args)
            if body.startswith(BLOCKED_MESSAGE):
                response = self._response(
                    body,
                    intent="blocked",
                    routing=routing,
                    blocked=True,
                    session_id=chat_session.id,
                )
                await self._persist_assistant(sessions, chat_session, response)
                return response
            await self._maybe_audit_command(principal, intent, args, body)
            response = self._response(
                body,
                intent=intent,
                routing=routing,
                session_id=chat_session.id,
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

        if self._policy.is_unsafe_request_text(text):
            await self._audit_blocked(principal, text, reason="unsafe_keyword")
            response = self._blocked_response(session_id=chat_session.id)
            async for event in self._emit_full_response(sessions, chat_session, response):
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
        }.get(intent)

        if handler:
            body = await handler(principal, args)
            if body.startswith(BLOCKED_MESSAGE):
                response = self._response(
                    body,
                    intent="blocked",
                    routing=routing,
                    blocked=True,
                    session_id=chat_session.id,
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

        if lowered in {"help", "?", "commands"}:
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

        if re.search(r"\b(run|execute|delete|write|send email|open browser|n8n)\b", lowered):
            return "blocked", {}

        return "general", {}

    async def _system_status(self, _principal: Principal, _args: dict[str, str]) -> str:
        availability = await get_worker_availability(self.session, self.settings)
        active = await self.session.execute(
            select(Mission).where(Mission.status == MissionStatus.RUNNING.value)
        )
        running = len(active.scalars().all())
        return (
            f"Control plane healthy. Workers online: {availability['workers_online']}/"
            f"{availability['workers_total']} (stale {availability['workers_stale']}, "
            f"offline {availability['workers_offline']}). Active missions: {running}."
        )

    async def _connected_devices(self, _principal: Principal, _args: dict[str, str]) -> str:
        svc = DeviceService(self.session, self.settings)
        devices = await svc.list_devices()
        if not devices:
            return "No connected devices."
        lines = [
            f"- {d.name} ({d.id}) type={d.device_type} status={d.status} conn={d.connection_status}"
            for d in devices
        ]
        return "Connected devices:\n" + "\n".join(lines)

    async def _worker_status(self, _principal: Principal, _args: dict[str, str]) -> str:
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

    async def _recent_missions(self, _principal: Principal, _args: dict[str, str]) -> str:
        result = await self.session.execute(
            select(Mission).order_by(Mission.created_at.desc()).limit(10)
        )
        missions = result.scalars().all()
        if not missions:
            return "No recent missions."
        lines = [f"- {m.title} ({m.mission_type}) status={m.status}" for m in missions]
        return "Recent missions:\n" + "\n".join(lines)

    async def _create_system_status_mission(
        self, principal: Principal, args: dict[str, str]
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

    async def _worker_capabilities(self, _principal: Principal, _args: dict[str, str]) -> str:
        from apps.worker.commands import execute_read_only_command

        payload = execute_read_only_command("configured_capabilities")
        caps = payload.get("capabilities", [])
        return "Worker capabilities:\n" + "\n".join(f"- {c}" for c in caps)

    async def _list_directory(self, principal: Principal, args: dict[str, str]) -> str:
        evaluation = self._policy.evaluate("list_directory", category="filesystem_read")
        if evaluation.decision != ToolDecision.AUTO_APPROVE:
            await self._audit_blocked(principal, args.get("path", ""), reason="policy_block")
            return BLOCKED_MESSAGE
        result = self._safe_tools.list_directory(args.get("path", "."))
        if not result.success:
            if self._is_safe_tool_policy_error(result.error):
                await self._audit_blocked(principal, args.get("path", ""), reason="safe_path_block")
                return BLOCKED_MESSAGE
            return f"Error: {result.error}"
        output = result.output
        assert isinstance(output, dict)
        entries = output.get("entries", [])
        names = ", ".join(str(e.get("name")) for e in entries[:20])
        return f"Directory {output.get('path')}: {names or '(empty)'}"

    async def _read_file(self, principal: Principal, args: dict[str, str]) -> str:
        evaluation = self._policy.evaluate("read_file", category="filesystem_read")
        if evaluation.decision != ToolDecision.AUTO_APPROVE:
            await self._audit_blocked(principal, args.get("path", ""), reason="policy_block")
            return BLOCKED_MESSAGE
        result = self._safe_tools.read_file(args.get("path", ""))
        if not result.success:
            if self._is_safe_tool_policy_error(result.error):
                await self._audit_blocked(principal, args.get("path", ""), reason="safe_path_block")
                return BLOCKED_MESSAGE
            return f"Error: {result.error}"
        output = result.output
        assert isinstance(output, dict)
        content = str(output.get("content", ""))
        preview = content[:1200] + ("…" if len(content) > 1200 else "")
        return f"File {output.get('path')} ({output.get('size')} bytes):\n{preview}"

    async def _ripgrep_search(self, principal: Principal, args: dict[str, str]) -> str:
        evaluation = self._policy.evaluate("ripgrep_search", category="search")
        if evaluation.decision != ToolDecision.AUTO_APPROVE:
            await self._audit_blocked(principal, args.get("pattern", ""), reason="policy_block")
            return BLOCKED_MESSAGE
        result = self._safe_tools.ripgrep_search(
            args.get("pattern", ""),
            args.get("path", "."),
        )
        if not result.success:
            if self._is_safe_tool_policy_error(result.error):
                await self._audit_blocked(
                    principal,
                    f"{args.get('pattern', '')} {args.get('path', '')}".strip(),
                    reason="safe_path_block",
                )
                return BLOCKED_MESSAGE
            return f"Error: {result.error}"
        output = result.output
        assert isinstance(output, dict)
        matches = output.get("matches", [])
        if not matches:
            return f"No matches for pattern `{output.get('pattern')}`."
        lines = [f"{m.get('path')}:{m.get('line')}: {m.get('text')}" for m in matches[:10]]
        suffix = " (truncated)" if output.get("truncated") else ""
        return f"Matches{suffix}:\n" + "\n".join(lines)

    async def _repo_analysis(self, principal: Principal, args: dict[str, str]) -> str:
        result = self._code_runtime.repo_analysis(args.get("path", "~/Projects/nova"))
        if not result.success:
            if self._is_safe_tool_policy_error(result.error):
                await self._audit_blocked(principal, args.get("path", ""), reason="safe_path_block")
                return BLOCKED_MESSAGE
            return f"Error: {result.error}"
        signals = result.output["signals"]
        return (
            f"Repo {result.output['repo']} has python={signals['python']}, "
            f"ios={signals['ios']}, docs={signals['docs']}, tests={signals['tests']}."
        )

    async def _explain_code(self, principal: Principal, args: dict[str, str]) -> str:
        result = self._code_runtime.explain_code(args.get("path", ""))
        if not result.success:
            if self._is_safe_tool_policy_error(result.error):
                await self._audit_blocked(principal, args.get("path", ""), reason="safe_path_block")
                return BLOCKED_MESSAGE
            return f"Error: {result.error}"
        return (
            f"{result.output['path']} has {result.output['line_count']} lines. "
            f"{result.output['summary']}"
        )

    async def _patch_plan(self, principal: Principal, args: dict[str, str]) -> str:
        await self._audit_blocked(
            principal,
            args.get("instruction", ""),
            reason="patch_generation_requires_approval",
        )
        result = self._code_runtime.patch_plan(args.get("instruction", ""))
        plan = "; ".join(result.output["plan"])
        return f"{BLOCKED_MESSAGE} Patch plan prepared for approval: {plan}."

    def _is_safe_tool_policy_error(self, error: str | None) -> bool:
        if not error:
            return False
        return error.startswith(("Blocked path segment:", "Path not in allowlist:"))

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

    def _blocked_response(self, *, session_id: str | None = None) -> dict[str, Any]:
        return {
            "response": BLOCKED_MESSAGE,
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
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "response": body,
            "intent": intent,
            "blocked": blocked,
            "session_id": session_id,
        }
        if token_usage is not None:
            payload["token_usage"] = token_usage
        if routing is not None:
            payload["routing"] = {
                "provider": routing.provider.value,
                "mode": routing.mode,
                "paid_call_allowed": routing.paid_call_allowed,
            }
        return payload
