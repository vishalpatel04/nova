"""Local access profiles for indexing and search roots."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from nova_core.memory.paths import canonicalize_path, path_within_root
from nova_core.memory.vault import is_vault_path


class AccessProfile(StrEnum):
    MINIMAL = "minimal"
    BROAD_LOCAL = "broad_local"
    FULL_LOCAL = "full_local"
    CUSTOM = "custom"


MINIMAL_ROOTS: tuple[str, ...] = (
    "~/Projects",
    "~/Desktop",
    "~/Documents",
    "~/Downloads",
)


@dataclass
class AccessPolicy:
    profile: AccessProfile
    include_paths: list[Path] = field(default_factory=list)
    exclude_paths: list[Path] = field(default_factory=list)
    override_performance_exclusions: bool = False
    indexing_paused: bool = False

    def allowed_roots(self) -> list[Path]:
        if self.profile == AccessProfile.MINIMAL:
            roots = [Path(os.path.expanduser(p)).resolve() for p in MINIMAL_ROOTS]
        elif self.profile in {AccessProfile.BROAD_LOCAL, AccessProfile.FULL_LOCAL}:
            roots = [Path.home().resolve()]
        else:
            roots = list(self.include_paths)
        filtered: list[Path] = []
        for root in roots:
            if is_vault_path(str(root)):
                continue
            filtered.append(root)
        return filtered

    def is_path_allowed(self, raw_path: str) -> bool:
        if is_vault_path(raw_path):
            return False
        canonical = canonicalize_path(raw_path)
        if canonical is None:
            return False
        resolved = canonical.resolved
        for exc in self.exclude_paths:
            if path_within_root(resolved, exc) or resolved == exc.resolve():
                return False
        return any(path_within_root(resolved, root) for root in self.allowed_roots())


def resolve_access_policy(
    *,
    profile: str | AccessProfile = AccessProfile.MINIMAL,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    override_performance: bool = False,
    indexing_paused: bool = False,
) -> AccessPolicy:
    prof = AccessProfile(profile) if isinstance(profile, str) else profile
    includes: list[Path] = []
    excludes: list[Path] = []
    for raw in include_paths or []:
        c = canonicalize_path(raw)
        if c is not None:
            includes.append(c.resolved)
    for raw in exclude_paths or []:
        c = canonicalize_path(raw)
        if c is not None and not is_vault_path(raw):
            excludes.append(c.resolved)
    return AccessPolicy(
        profile=prof,
        include_paths=includes,
        exclude_paths=excludes,
        override_performance_exclusions=override_performance,
        indexing_paused=indexing_paused,
    )


def default_minimal_policy() -> AccessPolicy:
    return resolve_access_policy(profile=AccessProfile.MINIMAL)
