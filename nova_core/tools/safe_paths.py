"""Allowlisted read-only filesystem paths for Phase 3A safe tools."""

from __future__ import annotations

import os
import re
from pathlib import Path

from nova_core.tools.protected_paths import (
    PROTECTED_PATH_MESSAGE,
    ProtectedPathError,
    is_protected_path,
)

BLOCKED_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"credentials", re.I),
    re.compile(r"token", re.I),
    re.compile(r"secret", re.I),
)

DEFAULT_ALLOWED_ROOTS: tuple[str, ...] = (
    "~/Projects/nova",
    "~/Desktop/NOVA-Safe-Test",
)


def expand_allowed_roots(roots: list[str] | None = None) -> list[Path]:
    configured = roots or list(DEFAULT_ALLOWED_ROOTS)
    return [Path(os.path.expanduser(p)).resolve() for p in configured]


def is_blocked_name(name: str) -> bool:
    from nova_core.tools.protected_paths import is_protected_filename

    if is_protected_filename(name):
        return True
    return any(pattern.search(name) for pattern in BLOCKED_NAME_PATTERNS)


def resolve_allowed_path(
    raw_path: str,
    *,
    allowed_roots: list[str] | None = None,
    must_exist: bool = False,
) -> Path:
    if is_protected_path(raw_path):
        raise ProtectedPathError(PROTECTED_PATH_MESSAGE)
    candidate = Path(os.path.expanduser(raw_path.strip())).resolve()
    roots = expand_allowed_roots(allowed_roots)
    if not any(candidate == root or root in candidate.parents for root in roots):
        raise PermissionError(f"Path not in allowlist: {candidate}")
    for part in candidate.parts:
        if is_blocked_name(part):
            raise PermissionError(f"Blocked path segment: {part}")
    if must_exist and not candidate.exists():
        raise FileNotFoundError(f"Path does not exist: {candidate}")
    return candidate
