"""Local wake-word parsing and voice approval safety."""

from __future__ import annotations

import re
from dataclasses import dataclass

WAKE_PHRASES: tuple[str, ...] = ("hey nova", "okay nova", "nova")

_EXPLICIT_SEND = frozenset(
    {
        "yes, send email",
        "yes send email",
        "yes, approve email",
        "send email",
    }
)
_EXPLICIT_DEPLOY = frozenset(
    {
        "yes, approve deployment",
        "yes approve deployment",
        "approve deployment",
    }
)


@dataclass(frozen=True)
class WakeParseResult:
    wake_detected: bool
    command: str
    wake_phrase: str | None = None


def parse_wake_command(transcript: str) -> WakeParseResult:
    text = transcript.strip()
    lowered = text.lower()
    for phrase in sorted(WAKE_PHRASES, key=len, reverse=True):
        if phrase in lowered:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            remainder = pattern.sub("", text, count=1).strip(" ,.-")
            return WakeParseResult(
                wake_detected=True,
                command=remainder,
                wake_phrase=phrase,
            )
    return WakeParseResult(wake_detected=False, command=text)


def requires_explicit_voice_approval(command: str, *, pending_kind: str | None) -> bool:
    if pending_kind not in {"orbit_email_send", "agent_os_deploy"}:
        return False
    lowered = command.lower().strip()
    if pending_kind == "orbit_email_send":
        return lowered not in _EXPLICIT_SEND
    if pending_kind == "agent_os_deploy":
        return lowered not in _EXPLICIT_DEPLOY
    return True


def is_wake_only(transcript: str) -> bool:
    parsed = parse_wake_command(transcript)
    return parsed.wake_detected and not parsed.command.strip()
