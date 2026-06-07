"""Patch path and payload policy validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nova_core.tools.protected_paths import PROTECTED_PATH_MESSAGE, is_protected_path

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".sh",
        ".swift",
        ".html",
        ".css",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
    }
)

BLOCKED_DIR_SEGMENTS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".venv",
        "vendor",
        "DerivedData",
        "dist",
        "build",
        ".git",
    }
)

BLOCKED_LOCKFILES: frozenset[str] = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "Gemfile.lock",
    }
)

MAX_FILE_BYTES = 256_000
MAX_FILES = 20
MAX_DIFF_LINES = 2000


@dataclass(frozen=True)
class PatchFileChange:
    relative_path: str
    action: str  # create | modify
    content: str


@dataclass
class PatchValidationResult:
    allowed: bool
    blocked: bool = False
    reason: str | None = None
    files: list[PatchFileChange] = field(default_factory=list)
    unified_diff: str = ""
    additions: int = 0
    deletions: int = 0


def _resolve_project_file(project_root: Path, relative_path: str) -> Path:
    rel = relative_path.strip().lstrip("/")
    if not rel or rel.startswith("..") or "/../" in f"/{rel}/":
        raise PermissionError("Blocked: path traversal outside project root.")
    candidate = (project_root / rel).resolve()
    if project_root not in candidate.parents and candidate != project_root:
        raise PermissionError("Blocked: path escapes project root.")
    if candidate.is_symlink():
        real = candidate.resolve()
        if project_root not in real.parents and real != project_root:
            raise PermissionError("Blocked: symlink escape outside project root.")
        candidate = real
    for segment in candidate.relative_to(project_root).parts:
        if segment in BLOCKED_DIR_SEGMENTS:
            raise PermissionError(f"Blocked: vendor/generated directory {segment!r}.")
    if is_protected_path(str(candidate)):
        raise PermissionError(PROTECTED_PATH_MESSAGE)
    if candidate.name in BLOCKED_LOCKFILES:
        raise PermissionError(f"Blocked: lockfile {candidate.name!r} not supported.")
    ext = candidate.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise PermissionError(f"Blocked: extension {ext!r} not allowlisted.")
    return candidate


def _is_text_utf8(content: str) -> bool:
    content.encode("utf-8")
    if "\x00" in content:
        raise ValueError("Blocked: binary content detected.")
    return True


def validate_patch_payload(
    project_root: Path,
    payload: dict[str, Any],
) -> PatchValidationResult:
    """Validate patch payload from approval metadata."""
    files_raw = payload.get("files")
    if not isinstance(files_raw, list) or not files_raw:
        return PatchValidationResult(
            allowed=False,
            blocked=True,
            reason="Blocked: patch payload missing files.",
        )
    if len(files_raw) > MAX_FILES:
        return PatchValidationResult(
            allowed=False,
            blocked=True,
            reason=f"Blocked: too many files (max {MAX_FILES}).",
        )

    unified_diff = str(payload.get("unified_diff", ""))
    if unified_diff.count("\n") > MAX_DIFF_LINES:
        return PatchValidationResult(
            allowed=False,
            blocked=True,
            reason="Blocked: diff too large.",
        )

    changes: list[PatchFileChange] = []
    additions = 0
    deletions = 0

    for entry in files_raw:
        if not isinstance(entry, dict):
            return PatchValidationResult(
                allowed=False, blocked=True, reason="Blocked: invalid file entry."
            )
        rel = str(entry.get("path", "")).strip()
        action = str(entry.get("action", "modify")).lower()
        if action not in {"create", "modify"}:
            return PatchValidationResult(
                allowed=False,
                blocked=True,
                reason=f"Blocked: action {action!r} not allowed (no delete/rename).",
            )
        content = str(entry.get("content", ""))
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            return PatchValidationResult(
                allowed=False,
                blocked=True,
                reason=f"Blocked: file {rel} exceeds size limit.",
            )
        try:
            _is_text_utf8(content)
            target = _resolve_project_file(project_root, rel)
        except (PermissionError, ValueError) as exc:
            return PatchValidationResult(allowed=False, blocked=True, reason=str(exc))
        if action == "modify" and not target.exists():
            return PatchValidationResult(
                allowed=False,
                blocked=True,
                reason=f"Blocked: cannot modify missing file {rel}.",
            )
        if action == "create" and target.exists():
            return PatchValidationResult(
                allowed=False,
                blocked=True,
                reason=f"Blocked: file already exists {rel}.",
            )
        old_lines = 0
        if target.exists():
            old_lines = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        new_lines = len(content.splitlines())
        additions += max(0, new_lines - old_lines)
        deletions += max(0, old_lines - new_lines)
        changes.append(PatchFileChange(relative_path=rel, action=action, content=content))

    return PatchValidationResult(
        allowed=True,
        files=changes,
        unified_diff=unified_diff[:8000],
        additions=additions,
        deletions=deletions,
    )


def build_patch_preview(payload: dict[str, Any]) -> str:
    files = payload.get("files") or []
    paths = [str(f.get("path", "")) for f in files if isinstance(f, dict)]
    diff = str(payload.get("unified_diff", ""))[:1200]
    summary = str(payload.get("summary", "Patch proposal"))
    return f"{summary}\nFiles ({len(paths)}): {', '.join(paths[:10])}\n\n{diff}"


def compute_patch_stats(unified_diff: str) -> tuple[int, int]:
    adds = len(re.findall(r"^\+[^+]", unified_diff, flags=re.MULTILINE))
    dels = len(re.findall(r"^-[^-]", unified_diff, flags=re.MULTILINE))
    return adds, dels
