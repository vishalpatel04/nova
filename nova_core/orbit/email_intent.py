"""Parse Orbit email draft and send intents from chat."""

from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL_DRAFT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)^draft an email to\s+(?P<recipient>.+?)\s+about\s+(?P<topic>.+?)$"),
    re.compile(r"(?i)^draft an email to\s+(?P<recipient>.+?)\s+sharing\s+(?P<topic>.+?)$"),
    re.compile(r"(?i)^draft an investor update email about\s+(?P<topic>.+?)$"),
    re.compile(r"(?i)^email this preview to\s+(?P<recipient>.+?)$"),
    re.compile(r"(?i)^draft an email about\s+(?P<topic>.+?)$"),
)

_SEND_YES = frozenset({"yes", "y", "approve", "send it", "send email"})
_SEND_NO = frozenset({"no", "n", "skip", "not now", "don't send", "dont send"})


@dataclass(frozen=True)
class EmailDraftRequest:
    raw_text: str
    recipient: str | None
    topic: str
    kind: str = "general"


def parse_email_draft_request(text: str) -> EmailDraftRequest | None:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return None
    for pattern in _EMAIL_DRAFT_PATTERNS:
        match = pattern.match(normalized)
        if not match:
            continue
        groups = match.groupdict()
        recipient = groups.get("recipient")
        topic = groups.get("topic") or "this app"
        kind = "investor_update" if "investor update" in normalized.lower() else "general"
        if recipient:
            recipient = recipient.strip().rstrip("?.!,")
        topic = topic.strip().rstrip("?.!,")
        return EmailDraftRequest(
            raw_text=normalized,
            recipient=recipient,
            topic=topic,
            kind=kind,
        )
    return None


def is_orbit_email_request(text: str) -> bool:
    return parse_email_draft_request(text) is not None


def resolve_email_send_intent(text: str, *, awaiting: bool) -> tuple[str, dict[str, str]] | None:
    lowered = text.lower().strip()
    if not awaiting:
        if lowered in {"send it", "send email"} and "draft" not in lowered:
            return "orbit_email_send_blocked", {}
        return None
    if lowered in _SEND_YES:
        return "orbit_email_send_yes", {}
    if lowered in _SEND_NO:
        return "orbit_email_send_no", {}
    return None
