"""Atomic patch application."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from nova_core.patch.policy import PatchValidationResult


@dataclass(frozen=True)
class PatchApplyResult:
    success: bool
    applied_files: tuple[str, ...]
    error: str | None = None


def apply_patch_payload(
    project_root: Path,
    validation: PatchValidationResult,
) -> PatchApplyResult:
    if not validation.allowed:
        return PatchApplyResult(success=False, applied_files=(), error=validation.reason)

    applied: list[str] = []
    backups: list[tuple[Path, bytes | None]] = []

    try:
        for change in validation.files:
            target = (project_root / change.relative_path).resolve()
            if project_root not in target.parents:
                raise PermissionError("Path escapes project root during apply.")
            target.parent.mkdir(parents=True, exist_ok=True)
            original: bytes | None = None
            if target.exists():
                original = target.read_bytes()
            backups.append((target, original))

            fd, tmp_path = tempfile.mkstemp(
                dir=str(target.parent),
                prefix=".nova_patch_",
                suffix=target.suffix,
            )
            os.close(fd)
            tmp = Path(tmp_path)
            try:
                tmp.write_text(change.content, encoding="utf-8")
                os.replace(tmp, target)
                applied.append(change.relative_path)
            finally:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)

        return PatchApplyResult(success=True, applied_files=tuple(applied))
    except Exception as exc:
        for target, original in reversed(backups):
            if original is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(original)
        return PatchApplyResult(success=False, applied_files=(), error=str(exc))
