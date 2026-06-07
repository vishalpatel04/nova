"""Active project root validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from nova_core.tools.protected_paths import PROTECTED_PATH_MESSAGE, is_protected_path
from nova_core.tools.safe_paths import expand_allowed_roots


@dataclass(frozen=True)
class ProjectRootValidation:
    allowed: bool
    resolved: Path | None = None
    reason: str | None = None


def validate_project_root(
    raw_path: str,
    *,
    allowed_roots: list[str] | None = None,
) -> ProjectRootValidation:
    if is_protected_path(raw_path):
        return ProjectRootValidation(allowed=False, reason=PROTECTED_PATH_MESSAGE)

    expanded = Path(os.path.expanduser(raw_path.strip()))
    try:
        resolved = expanded.resolve()
    except OSError as exc:
        return ProjectRootValidation(allowed=False, reason=f"Blocked: invalid path ({exc}).")

    if not resolved.is_dir():
        return ProjectRootValidation(
            allowed=False, reason="Blocked: project root must be a directory."
        )

    roots = expand_allowed_roots(allowed_roots)
    if not any(resolved == root or root in resolved.parents for root in roots):
        return ProjectRootValidation(
            allowed=False,
            reason=f"Blocked: path not in allowlist ({resolved}).",
        )

    if expanded.is_symlink():
        real = expanded.resolve()
        if not any(real == root or root in real.parents for root in roots):
            return ProjectRootValidation(
                allowed=False,
                reason="Blocked: symlink escape outside allowlist.",
            )
        if is_protected_path(str(real)):
            return ProjectRootValidation(allowed=False, reason=PROTECTED_PATH_MESSAGE)

    return ProjectRootValidation(allowed=True, resolved=resolved)
