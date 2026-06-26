"""Sentry — independent risk review and secret redaction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from nova_core.agent_os.workspace import redact_secrets

BLOCKED_CLAIM_PATTERNS = (
    re.compile(r"(?i)deployed to production"),
    re.compile(r"(?i)successfully pushed to remote"),
    re.compile(r"(?i)payment processed"),
)

DESTRUCTIVE_COMMANDS = (
    "rm -rf",
    "rm -r /",
    "mkfs",
    "dd if=",
    "shutdown",
    "reboot",
    ":(){ :|:& };:",
)


@dataclass(frozen=True)
class SentryVerdict:
    allowed: bool
    requires_approval: bool
    reason: str
    redacted: bool = False


def review_action(action: str, *, context: dict[str, Any] | None = None) -> SentryVerdict:
    action_l = action.lower().strip()
    ctx = context or {}

    for destructive in DESTRUCTIVE_COMMANDS:
        if destructive in action_l:
            return SentryVerdict(
                allowed=False,
                requires_approval=False,
                reason=f"Blocked destructive command pattern: {destructive}",
            )

    if action_l in {"deploy.vercel_deploy", "deploy.external", "git.push"}:
        return SentryVerdict(
            allowed=False,
            requires_approval=True,
            reason="External action requires explicit user approval",
        )

    if action_l.startswith("deploy."):
        return SentryVerdict(
            allowed=True,
            requires_approval=action_l.endswith("_deploy"),
            reason="Deployment prepare allowed; deploy requires approval",
        )

    if ctx.get("outside_workspace") and not ctx.get("approved"):
        return SentryVerdict(
            allowed=False,
            requires_approval=True,
            reason="Write outside workspace requires approval",
        )

    return SentryVerdict(allowed=True, requires_approval=False, reason="Action permitted")


def block_unsupported_completion_claim(text: str) -> str:
    for pattern in BLOCKED_CLAIM_PATTERNS:
        if pattern.search(text):
            return (
                "Sentry blocked unsupported completion claim. "
                "Provide evidence or request approval for external actions."
            )
    return redact_secrets(text)


def sanitize_log_line(line: str) -> str:
    return redact_secrets(line)
