"""Canonical path normalization and symlink escape prevention."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from nova_core.memory.vault import assert_not_vault_path, is_vault_path


@dataclass(frozen=True)
class CanonicalPath:
    raw: str
    resolved: Path
    canonical: str


def canonicalize_path(raw_path: str) -> CanonicalPath | None:
    expanded = os.path.expanduser(raw_path.strip())
    if not expanded:
        return None
    if is_vault_path(expanded):
        return None
    candidate = Path(expanded)
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if is_vault_path(str(resolved)):
        return None
    return CanonicalPath(raw=raw_path.strip(), resolved=resolved, canonical=str(resolved))


def path_within_root(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return candidate.resolve() == root.resolve()


def assert_path_within_roots(candidate: Path, roots: list[Path]) -> None:
    assert_not_vault_path(str(candidate))
    if not any(path_within_root(candidate, root) for root in roots):
        raise PermissionError("Path is outside approved local knowledge roots.")


def symlink_escapes_root(link: Path, root: Path) -> bool:
    if not link.is_symlink():
        return False
    try:
        target = link.resolve()
    except OSError:
        return True
    return not path_within_root(target, root)
