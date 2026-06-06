"""Approval-gated automation runtime for Phase 3B."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nova_core.automation.base import AutomationProviderKind, AutomationResult
from nova_core.schemas.settings import Settings

SAFE_ACTIONS: frozenset[str] = frozenset(
    {
        "status",
        "list_workflows",
        "list_shortcuts",
        "list_agents",
        "dry_run",
    }
)


@dataclass(frozen=True)
class AutomationRequest:
    provider: AutomationProviderKind
    action: str
    payload: dict[str, Any]
    approved: bool = False
    dry_run: bool = False


class AutomationRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def execute(self, request: AutomationRequest) -> AutomationResult:
        if request.dry_run or request.action in SAFE_ACTIONS:
            return AutomationResult(
                success=True,
                output={
                    "provider": request.provider.value,
                    "action": request.action,
                    "dry_run": True,
                    "would_execute": request.payload,
                },
                requires_approval=request.action not in SAFE_ACTIONS,
            )
        if not request.approved:
            return AutomationResult(
                success=False,
                error="Blocked: automation execution requires explicit approval.",
                requires_approval=True,
            )
        if request.provider == AutomationProviderKind.N8N:
            return await self._execute_n8n(request)
        if request.provider == AutomationProviderKind.OPENCLAW:
            return await self._execute_openclaw(request)
        if request.provider == AutomationProviderKind.SHORTCUTS:
            return await self._execute_shortcuts(request)
        return AutomationResult(success=False, error="Unsupported automation provider")

    async def _execute_n8n(self, request: AutomationRequest) -> AutomationResult:
        _ = request
        return AutomationResult(
            success=False,
            error="Blocked: n8n execution is not enabled in Phase 3B runtime.",
            requires_approval=True,
        )

    async def _execute_openclaw(self, request: AutomationRequest) -> AutomationResult:
        _ = request
        return AutomationResult(
            success=False,
            error="Blocked: OpenClaw execution is not enabled in Phase 3B runtime.",
            requires_approval=True,
        )

    async def _execute_shortcuts(self, request: AutomationRequest) -> AutomationResult:
        if not self.settings.nova_shortcuts_enabled:
            return AutomationResult(success=False, error="Apple Shortcuts execution is not enabled")
        return AutomationResult(
            success=False,
            error=(
                "Apple Shortcuts requires a signed native runner; API approval and audit are ready."
            ),
            requires_approval=True,
        )
