"""Tool approval policy — read-only allowlist auto-approved; dangerous actions blocked."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

BLOCKED_MESSAGE = (
    "Blocked: this action requires approval/policy support and is not implemented yet."
)


class ToolDecision(StrEnum):
    AUTO_APPROVE = "auto_approve"
    BLOCK = "block"


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: ToolDecision
    tool_name: str
    category: str
    reason: str | None = None


READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "list_directory",
        "read_file",
        "ripgrep_search",
        "system_status",
        "hostname",
        "uptime",
        "operating_system_version",
        "cpu_architecture",
        "configured_capabilities",
    }
)

BLOCKED_TOOL_PATTERNS: tuple[str, ...] = (
    "shell",
    "execute",
    "write",
    "delete",
    "move",
    "email",
    "gmail",
    "browser",
    "desktop",
    "n8n",
    "openclaw",
    "shortcut",
    "automation_run",
)


class ToolPolicy:
    def __init__(self, policies: dict[str, Any] | None = None) -> None:
        self._policies = policies or {}
        approval = self._policies.get("approval", {})
        self._auto_categories = set(approval.get("auto_approve_categories", []))
        self._required_categories = set(approval.get("required_categories", []))

    def evaluate(self, tool_name: str, *, category: str = "filesystem_read") -> PolicyEvaluation:
        lowered = tool_name.lower()
        if any(blocked in lowered for blocked in BLOCKED_TOOL_PATTERNS):
            return PolicyEvaluation(
                decision=ToolDecision.BLOCK,
                tool_name=tool_name,
                category=category,
                reason=BLOCKED_MESSAGE,
            )
        if category in self._required_categories:
            return PolicyEvaluation(
                decision=ToolDecision.BLOCK,
                tool_name=tool_name,
                category=category,
                reason=BLOCKED_MESSAGE,
            )
        if tool_name in READ_ONLY_TOOLS or category in self._auto_categories:
            return PolicyEvaluation(
                decision=ToolDecision.AUTO_APPROVE,
                tool_name=tool_name,
                category=category,
            )
        return PolicyEvaluation(
            decision=ToolDecision.BLOCK,
            tool_name=tool_name,
            category=category,
            reason=BLOCKED_MESSAGE,
        )

    def is_unsafe_request_text(self, message: str) -> bool:
        lowered = message.lower()
        unsafe_keywords = (
            "run shell",
            "execute command",
            "delete file",
            "write file",
            "send email",
            "open browser",
            "control desktop",
            "run n8n",
            "openclaw",
            "rm -rf",
            "sudo ",
        )
        return any(keyword in lowered for keyword in unsafe_keywords)
