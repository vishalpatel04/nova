"""Lightweight @agent mention routing for NOVAGenie War Room."""

from __future__ import annotations

import re

_MENTION_RE = re.compile(r"^@(\w+)\s+(.*)$", re.DOTALL)

_AGENT_ALIASES: dict[str, str] = {
    "prime": "prime",
    "forge": "forge",
    "archive": "archive",
    "sentry": "sentry",
    "orbit": "orbit",
    "muse": "muse",
    "qa": "qa",
    "nexus": "nexus",
}


def parse_agent_mention(text: str) -> tuple[str | None, str]:
    match = _MENTION_RE.match(text.strip())
    if not match:
        return None, text
    agent = _AGENT_ALIASES.get(match.group(1).lower())
    if agent is None:
        return None, text
    return agent, match.group(2).strip()


def route_mention_intent(agent: str, body: str) -> tuple[str, dict[str, str]] | None:
    """Map @agent prefix to closest existing chat intent handler."""
    if not body.strip():
        return None
    lowered = body.lower()
    status_words = (
        "what",
        "status",
        "doing",
        "need",
        "approval",
        "summarize",
        "summary",
        "engine",
        "validation",
        "context",
        "happened",
    )
    if any(word in lowered for word in status_words) and agent in {
        "prime",
        "forge",
        "archive",
        "nexus",
    }:
        return "agent_awareness", {"agent": agent, "request": body}
    if agent == "forge":
        return "agent_os_mission", {"request": body}
    if agent == "archive":
        lowered = body.lower()
        if lowered.startswith("find "):
            return "archive_search", {"query": body[5:].strip()}
        if "search" in lowered:
            return "archive_search", {"query": body}
        return "memory_recall", {"topic": body}
    if agent == "orbit":
        return "orbit_email_draft", {"request": body}
    if agent == "sentry":
        return "sentry_summary", {"request": body}
    if agent == "qa":
        return "qa_status", {"request": body}
    if agent == "muse":
        if any(word in body.lower() for word in ("build", "landing", "page", "app")):
            return "agent_os_mission", {"request": body}
        return "general", {"message": body, "requested_agent": "muse"}
    if agent == "nexus":
        return "system_status", {}
    if agent == "prime":
        return "general", {"message": body, "requested_agent": "prime"}
    return None
