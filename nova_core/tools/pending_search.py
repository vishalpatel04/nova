"""Deterministic parsing for personal-search scope confirmation follow-ups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nova_core.tools.search_scopes import SEARCH_ROOT_ALIASES, normalize_search_path

ScopeReplyAction = Literal["scope_path", "all_approved", "cancel", "unrelated"]

ALL_APPROVED_REPLIES: frozenset[str] = frozenset(
    {
        "all",
        "all approved folders",
        "yes",
        "y",
    }
)

CANCEL_REPLIES: frozenset[str] = frozenset(
    {
        "no",
        "cancel",
        "n",
    }
)

SUGGESTED_SCOPE_LABELS: tuple[str, ...] = ("Desktop", "Documents", "Downloads", "Projects")

PENDING_SCOPE_PROMPT = (
    "Waiting for folder choice: Desktop, Documents, Downloads, Projects, or all approved folders"
)


@dataclass(frozen=True)
class ScopeConfirmationReply:
    action: ScopeReplyAction
    path: str | None = None


def _scope_path_from_label(label: str) -> str | None:
    normalized = normalize_search_path(label.strip())
    if normalized.startswith("~/"):
        return normalized
    alias = SEARCH_ROOT_ALIASES.get(label.strip().lower())
    if alias:
        return alias
    return None


def parse_scope_confirmation_reply(text: str) -> ScopeConfirmationReply:
    normalized = text.strip().lower()
    if not normalized:
        return ScopeConfirmationReply(action="unrelated")

    if normalized in CANCEL_REPLIES:
        return ScopeConfirmationReply(action="cancel")

    if normalized in ALL_APPROVED_REPLIES:
        return ScopeConfirmationReply(action="all_approved")

    scope_path = _scope_path_from_label(text)
    if scope_path is not None:
        return ScopeConfirmationReply(action="scope_path", path=scope_path)

    return ScopeConfirmationReply(action="unrelated")


def scope_confirmation_prompt(query: str) -> str:
    return (
        "I can search Desktop, Documents, Downloads, and Projects.\n"
        'Choose a folder or say "all approved folders".\n\n'
        f"{PENDING_SCOPE_PROMPT}"
    )


def unrelated_pending_message(query: str) -> str:
    return (
        f'Waiting for folder choice for "{query}": Desktop, Documents, Downloads, '
        f"Projects, or all approved folders.\n"
        'Or say "cancel" to dismiss.'
    )
