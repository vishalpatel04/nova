"""NOVA_VAULT permanent invisibility — no reads, metadata, or traversal."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

VAULT_DIR_NAME = "NOVA_VAULT"

VAULT_INVISIBLE_MESSAGE = (
    "Blocked: NOVA_VAULT is permanently inaccessible to NOVA. "
    "No reads, search, metadata, indexing, or traversal are permitted."
)


class VaultAccessError(PermissionError):
    """Raised when any operation touches NOVA_VAULT."""


def vault_root() -> Path:
    return (Path.home() / VAULT_DIR_NAME).resolve()


def _normalize_raw_path(raw_path: str) -> str:
    text = raw_path.strip()
    if text.lower().startswith("file://"):
        parsed = urlparse(text)
        return unquote(parsed.path)
    return os.path.expanduser(text)


def is_vault_path(raw_path: str) -> bool:
    """True if path is inside ~/NOVA_VAULT (including symlinks resolving into vault)."""
    if not raw_path.strip():
        return False
    expanded = _normalize_raw_path(raw_path)
    if not expanded:
        return False
    candidate = Path(expanded)
    root = vault_root()
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate
    try:
        if resolved == root or root in resolved.parents:
            return True
    except OSError:
        return False
    return VAULT_DIR_NAME in resolved.parts


def assert_not_vault_path(raw_path: str) -> None:
    if is_vault_path(raw_path):
        raise VaultAccessError(VAULT_INVISIBLE_MESSAGE)


def sanitize_for_external_response(raw_path: str) -> str:
    """Never leak vault filenames in API responses."""
    if is_vault_path(raw_path):
        return "[vault: redacted]"
    return raw_path
