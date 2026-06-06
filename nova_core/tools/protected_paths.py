"""Protected path boundaries — vault, credentials, and secrets."""

from __future__ import annotations

import os
import re
from pathlib import Path

PROTECTED_PATH_MESSAGE = (
    "Blocked: this path is protected (vault, credentials, or secrets). "
    "NOVA will not read or send it to any provider."
)

PROTECTED_BASENAMES: frozenset[str] = frozenset({"id_rsa", "id_ed25519"})

PROTECTED_FILENAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\.env", re.I),
    re.compile(r"\.env$", re.I),
    re.compile(r"\.pem$", re.I),
    re.compile(r"\.key$", re.I),
    re.compile(r"\.p12$", re.I),
    re.compile(r"^id_rsa", re.I),
    re.compile(r"^id_ed25519", re.I),
)


class ProtectedPathError(PermissionError):
    """Raised when a path is in the protected vault/credentials boundary."""


def protected_roots() -> list[Path]:
    home = Path.home()
    return [
        (home / "NOVA_VAULT").resolve(),
        (home / ".ssh").resolve(),
        (home / ".aws").resolve(),
        (home / ".config").resolve(),
    ]


def is_protected_filename(name: str) -> bool:
    if name in PROTECTED_BASENAMES:
        return True
    return any(pattern.search(name) for pattern in PROTECTED_FILENAME_PATTERNS)


def is_protected_path(raw_path: str) -> bool:
    expanded = os.path.expanduser(raw_path.strip())
    if not expanded:
        return False
    candidate = Path(expanded)
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate

    for root in protected_roots():
        try:
            if resolved == root or root in resolved.parents:
                return True
        except OSError:
            continue

    if is_protected_filename(resolved.name):
        return True

    for part in resolved.parts:
        if part == ".env" or part.startswith(".env."):
            return True
        if is_protected_filename(part):
            return True

    return False


def sanitize_path_for_log(raw_path: str) -> str:
    """Return a short label for audit/logs — never full secret paths."""
    name = Path(os.path.expanduser(raw_path.strip())).name
    if is_protected_filename(name):
        return f"protected:{name}"
    if name:
        return name
    return "protected_path"


def assert_path_not_protected(raw_path: str) -> None:
    if is_protected_path(raw_path):
        raise ProtectedPathError(PROTECTED_PATH_MESSAGE)
