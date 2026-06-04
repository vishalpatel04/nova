"""Chat command routing and safe tool orchestration."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.devices import DeviceService
from apps.api.services.missions import MissionService
from nova_core.auth.principal import Principal
from nova_core.devices.availability import get_worker_availability
from nova_core.models.enums import MissionStatus
from nova_core.models.orm import Mission
from nova_core.providers.router import ProviderConfig, ProviderRouter
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
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
        self._router = ProviderRouter(ProviderConfig())

    async def handle_message(
        self,
        *,
        message: str,
        principal: Principal,
    ) -> dict[str, Any]:
        text = message.strip()
        if not text:
            return self._response("Please enter a message.", intent="empty")

        if self._policy.is_unsafe_request_text(text):
            await self._audit_blocked(principal, text, reason="unsafe_keyword")
            return self._blocked_response()

        intent, args = self._parse_intent(text)
        routing = self._router.route(text, intent=intent)

        if intent == "help":
            return self._response(HELP_TEXT, intent=intent, routing=routing)

        if intent == "blocked":
            await self._audit_blocked(principal, text, reason="blocked_intent")
            return self._blocked_response()

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
        }.get(intent)

        if handler:
            body = await handler(principal, args)
            if body == BLOCKED_MESSAGE:
                return self._response(
                    body,
                    intent="blocked",
                    routing=routing,
                    blocked=True,
                )
            await self._maybe_audit_command(principal, intent, args, body)
            return self._response(body, intent=intent, routing=routing)

        stub = await self._router.invoke_stub(routing, text)
        return self._response(stub["response"], intent="general", routing=routing)

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

    def _blocked_response(self) -> dict[str, Any]:
        return {
            "response": BLOCKED_MESSAGE,
            "intent": "blocked",
            "blocked": True,
        }

    def _response(
        self,
        body: str,
        *,
        intent: str,
        routing: Any | None = None,
        blocked: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "response": body,
            "intent": intent,
            "blocked": blocked,
        }
        if routing is not None:
            payload["routing"] = {
                "provider": routing.provider.value,
                "mode": routing.mode,
                "paid_call_allowed": routing.paid_call_allowed,
            }
        return payload
