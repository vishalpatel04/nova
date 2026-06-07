"""Unified diff helpers for patch proposals."""

from __future__ import annotations

import difflib
from pathlib import Path

from nova_core.patch.policy import PatchFileChange


def build_unified_diff(
    project_root: Path,
    changes: list[PatchFileChange],
) -> str:
    lines: list[str] = []
    for change in changes:
        rel = change.relative_path
        target = project_root / rel
        old_lines: list[str] = []
        if change.action == "modify" and target.exists():
            old_lines = target.read_text(encoding="utf-8", errors="replace").splitlines(
                keepends=True
            )
        new_lines = change.content.splitlines(keepends=True)
        if not new_lines and change.content:
            new_lines = [change.content + "\n"]
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            lineterm="",
        )
        lines.extend(diff)
        if lines and not lines[-1].endswith("\n"):
            lines.append("")
    return "\n".join(lines)
