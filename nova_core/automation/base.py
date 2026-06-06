"""Automation provider scaffold — execution disabled in Phase 3A."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

NOT_IMPLEMENTED_MESSAGE = (
    "Blocked: this action requires approval/policy support and is not implemented yet."
)


class AutomationProviderKind(StrEnum):
    N8N = "n8n"
    OPENCLAW = "openclaw"
    SHORTCUTS = "shortcuts"


@dataclass(frozen=True)
class AutomationResult:
    success: bool
    output: Any = None
    error: str | None = None
    requires_approval: bool = True


class AutomationProvider(ABC):
    kind: AutomationProviderKind
    enabled: bool = False

    @abstractmethod
    async def execute(
        self, action: str, payload: dict[str, Any] | None = None
    ) -> AutomationResult: ...


class StubAutomationProvider(AutomationProvider):
    def __init__(self, kind: AutomationProviderKind) -> None:
        self.kind = kind
        self.enabled = False

    async def execute(self, action: str, payload: dict[str, Any] | None = None) -> AutomationResult:
        return AutomationResult(
            success=False,
            error=NOT_IMPLEMENTED_MESSAGE,
            requires_approval=True,
        )


class AutomationRegistry:
    def __init__(self) -> None:
        self._providers: dict[AutomationProviderKind, AutomationProvider] = {
            AutomationProviderKind.N8N: StubAutomationProvider(AutomationProviderKind.N8N),
            AutomationProviderKind.OPENCLAW: StubAutomationProvider(
                AutomationProviderKind.OPENCLAW
            ),
            AutomationProviderKind.SHORTCUTS: StubAutomationProvider(
                AutomationProviderKind.SHORTCUTS
            ),
        }

    def get(self, kind: AutomationProviderKind) -> AutomationProvider:
        return self._providers[kind]

    def list_planned(self) -> list[str]:
        return [kind.value for kind in AutomationProviderKind]
