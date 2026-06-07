"""Read-only personal-folder search scopes — separate from project editing allowlists."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from nova_core.tools.protected_paths import PROTECTED_PATH_MESSAGE, is_protected_path

DEFAULT_SEARCH_ROOTS: tuple[str, ...] = (
    "~/Projects",
    "~/Desktop",
    "~/Documents",
    "~/Downloads",
)

SEARCH_ROOT_ALIASES: dict[str, str] = {
    "projects": "~/Projects",
    "desktop": "~/Desktop",
    "documents": "~/Documents",
    "downloads": "~/Downloads",
}

SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "DerivedData",
        "Library",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
    }
)

MAX_SEARCH_DEPTH = 12
MAX_FILES_SCANNED = 2000
MAX_DISPLAY_MATCHES = 25


@dataclass(frozen=True)
class SearchScopeValidation:
    allowed: bool
    resolved: Path | None = None
    reason: str | None = None


def expand_search_roots(configured: list[str] | None = None) -> list[Path]:
    roots = configured or list(DEFAULT_SEARCH_ROOTS)
    return [Path(os.path.expanduser(p)).resolve() for p in roots]


def normalize_search_path(raw_path: str) -> str:
    text = raw_path.strip()
    if not text or text == ".":
        return text
    lowered = text.lower().rstrip("/")
    if lowered in SEARCH_ROOT_ALIASES:
        return SEARCH_ROOT_ALIASES[lowered]
    for label, canonical in SEARCH_ROOT_ALIASES.items():
        if lowered == label or lowered == f"~/{label}":
            return canonical
    if text.startswith("~/"):
        return text
    return text


def _path_within_root(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return candidate == root


def resolve_search_scope(
    raw_path: str,
    *,
    search_roots: list[str] | None = None,
) -> SearchScopeValidation:
    normalized = normalize_search_path(raw_path)
    if is_protected_path(normalized):
        return SearchScopeValidation(allowed=False, reason=PROTECTED_PATH_MESSAGE)

    expanded = Path(os.path.expanduser(normalized.strip()))
    try:
        resolved = expanded.resolve()
    except OSError as exc:
        return SearchScopeValidation(allowed=False, reason=f"Blocked: invalid path ({exc}).")

    if "Library" in resolved.parts:
        return SearchScopeValidation(
            allowed=False,
            reason="Blocked: system Library folders are not searchable.",
        )

    if "NOVA_VAULT" in resolved.parts:
        return SearchScopeValidation(allowed=False, reason=PROTECTED_PATH_MESSAGE)

    roots = expand_search_roots(search_roots)
    if not any(_path_within_root(resolved, root) for root in roots):
        return SearchScopeValidation(
            allowed=False,
            reason=(
                "Blocked: search path must be under approved folders "
                "(Projects, Desktop, Documents, Downloads)."
            ),
        )

    if is_protected_path(str(resolved)):
        return SearchScopeValidation(allowed=False, reason=PROTECTED_PATH_MESSAGE)

    if expanded.is_symlink():
        real = expanded.resolve()
        if not any(_path_within_root(real, root) for root in roots):
            return SearchScopeValidation(
                allowed=False,
                reason="Blocked: symlink escape outside approved search roots.",
            )
        if is_protected_path(str(real)):
            return SearchScopeValidation(allowed=False, reason=PROTECTED_PATH_MESSAGE)

    if not resolved.exists():
        return SearchScopeValidation(allowed=False, reason=f"Path does not exist: {resolved}")

    return SearchScopeValidation(allowed=True, resolved=resolved)


def resolve_all_approved_scopes(
    *,
    search_roots: list[str] | None = None,
) -> list[Path]:
    return expand_search_roots(search_roots)


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or (name.startswith(".") and name not in {".", ".."})


def should_skip_file(path: Path) -> bool:
    if is_protected_path(str(path)):
        return True
    name = path.name
    if name.startswith("."):
        return True
    if any(name.endswith(suffix) for suffix in (".pem", ".key", ".p12", ".pfx", ".keystore")):
        return True
    if name in {"id_rsa", "id_ed25519"}:
        return True
    return bool(re.search(r"\.env", name, re.I))


def is_probably_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(8192)
    except OSError:
        return True
    if b"\x00" in chunk:
        return True
    if not chunk:
        return False
    text_chars = sum(1 for byte in chunk if byte in (9, 10, 13) or 32 <= byte <= 126)
    return text_chars / len(chunk) < 0.85
