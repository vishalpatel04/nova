"""Parse Orbit email draft, edit, and send intents from chat."""

from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL_DRAFT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)^draft an email to\s+(?P<recipient>.+?)\s+about\s+(?P<topic>.+?)$"),
    re.compile(r"(?i)^draft an email to\s+(?P<recipient>.+?)\s+sharing\s+(?P<topic>.+?)$"),
    re.compile(r"(?i)^draft an investor update email about\s+(?P<topic>.+?)$"),
    re.compile(r"(?i)^draft an investor update about\s+(?P<topic>.+?)$"),
    re.compile(r"(?i)^email this preview to\s+(?P<recipient>.+?)$"),
    re.compile(r"(?i)^mail the latest preview to\s+(?P<recipient>.+?)$"),
    re.compile(r"(?i)^draft an email about\s+(?P<topic>.+?)$"),
    re.compile(r"(?i)^draft a short professional follow-?up(?:\s+to\s+(?P<recipient>.+?))?$"),
    re.compile(r"(?i)^draft an email to\s+(?P<recipient>.+?)$"),
    re.compile(r"(?i)^send this to\s+(?P<recipient>.+?)$"),
    re.compile(r"(?i)^email this to\s+(?P<recipient>.+?)$"),
)

_SEND_YES = frozenset({"yes", "y", "approve", "send it", "send email"})
_SEND_NO = frozenset({"no", "n", "skip", "not now", "don't send", "dont send"})
_EXPLICIT_SEND_YES = frozenset(
    {
        "yes, send email",
        "yes send email",
        "yes, approve email",
        "yes approve email",
        "send email",
        "approve email send",
    }
)
_EXPLICIT_DEPLOY_YES = frozenset(
    {
        "yes, approve deployment",
        "yes approve deployment",
        "yes, deploy",
        "approve deployment",
    }
)

_EMAIL_EDIT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)^(make it shorter|make shorter|shorter)$"),
    re.compile(r"(?i)^(edit it|edit the email|change it)$"),
    re.compile(r"(?i).*(more investor|investor-like|investor tone).*"),
    re.compile(r"(?i).*(more confident|confident tone).*"),
    re.compile(r"(?i).*(change tone|different tone).*"),
    re.compile(r"(?i)^(send to someone else|different recipient)$"),
)


@dataclass(frozen=True)
class EmailDraftRequest:
    raw_text: str
    recipient: str | None
    topic: str
    kind: str = "general"
    purpose: str = "general"


@dataclass(frozen=True)
class EmailEditRequest:
    raw_text: str
    instruction: str


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
        lowered = normalized.lower()
        kind = "investor_update" if "investor update" in lowered else "general"
        purpose = "follow_up" if "follow-up" in lowered or "follow up" in lowered else kind
        if recipient:
            recipient = recipient.strip().rstrip("?.!,")
        topic = topic.strip().rstrip("?.!,")
        return EmailDraftRequest(
            raw_text=normalized,
            recipient=recipient,
            topic=topic,
            kind=kind,
            purpose=purpose,
        )
    return None


def is_orbit_email_request(text: str) -> bool:
    return parse_email_draft_request(text) is not None


def parse_email_edit_request(text: str) -> EmailEditRequest | None:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return None
    for pattern in _EMAIL_EDIT_PATTERNS:
        if pattern.match(normalized) or pattern.search(normalized):
            return EmailEditRequest(raw_text=normalized, instruction=normalized)
    return None


def resolve_email_send_intent(
    text: str,
    *,
    awaiting: bool,
    explicit_only: bool = False,
) -> tuple[str, dict[str, str]] | None:
    lowered = text.lower().strip()
    if not awaiting:
        if lowered in {"send it", "send email"} and "draft" not in lowered:
            return "orbit_email_send_blocked", {}
        return None
    if explicit_only:
        if lowered in _EXPLICIT_SEND_YES:
            return "orbit_email_send_yes", {}
        if lowered in _SEND_NO:
            return "orbit_email_send_no", {}
        return None
    if lowered in _SEND_YES or lowered in _EXPLICIT_SEND_YES:
        return "orbit_email_send_yes", {}
    if lowered in _SEND_NO:
        return "orbit_email_send_no", {}
    return None


def is_explicit_deploy_approval(text: str) -> bool:
    return text.lower().strip() in _EXPLICIT_DEPLOY_YES
