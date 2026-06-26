"""Contact resolution for Orbit email flows."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from nova_core.agent_os.workspace import workspace_root

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


@dataclass(frozen=True)
class ContactResolution:
    email: str | None
    display_name: str | None
    source: str
    ambiguous: bool = False
    candidates: tuple[str, ...] = ()


def _contacts_cache_path() -> Path:
    path = workspace_root() / ".nova-contacts-cache.json"
    return path


def load_contacts_cache() -> dict[str, str]:
    path = _contacts_cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key).lower(): str(value) for key, value in data.items()}


def save_contact_alias(name: str, email: str) -> None:
    cache = load_contacts_cache()
    cache[name.strip().lower()] = email.strip()
    path = _contacts_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def resolve_contact(name_or_email: str | None) -> ContactResolution:
    if not name_or_email or not name_or_email.strip():
        return ContactResolution(email=None, display_name=None, source="missing", ambiguous=True)
    cleaned = name_or_email.strip().rstrip("?.!,")
    if _EMAIL_RE.match(cleaned):
        return ContactResolution(email=cleaned, display_name=None, source="explicit_email")
    lowered = cleaned.lower()
    cache = load_contacts_cache()
    if lowered in cache:
        return ContactResolution(
            email=cache[lowered],
            display_name=cleaned,
            source="local_cache",
        )
    slug = re.sub(r"[^a-z0-9]+", "", lowered)
    matches = [email for key, email in cache.items() if slug and slug in key.replace(" ", "")]
    if len(matches) == 1:
        return ContactResolution(
            email=matches[0],
            display_name=cleaned,
            source="local_cache_fuzzy",
        )
    if len(matches) > 1:
        return ContactResolution(
            email=None,
            display_name=cleaned,
            source="local_cache_ambiguous",
            ambiguous=True,
            candidates=tuple(matches),
        )
    return ContactResolution(
        email=None,
        display_name=cleaned,
        source="unresolved",
        ambiguous=True,
    )
