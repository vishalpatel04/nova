"""Typed read-only filesystem tools — no writes, shell, or network."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nova_core.tools.safe_paths import resolve_allowed_path


@dataclass(frozen=True)
class SafeToolResult:
    success: bool
    output: Any = None
    error: str | None = None


class SafeReadonlyTools:
    def __init__(self, allowed_roots: list[str] | None = None) -> None:
        self._allowed_roots = allowed_roots

    def list_directory(self, path: str = ".", *, limit: int = 200) -> SafeToolResult:
        try:
            resolved = resolve_allowed_path(
                path, allowed_roots=self._allowed_roots, must_exist=True
            )
            if not resolved.is_dir():
                return SafeToolResult(success=False, error="Path is not a directory")
            entries: list[dict[str, str | bool]] = []
            for entry in sorted(resolved.iterdir(), key=lambda p: p.name.lower())[:limit]:
                if any(part.startswith(".") and part != "." for part in entry.parts):
                    continue
                entries.append(
                    {
                        "name": entry.name,
                        "path": str(entry),
                        "is_dir": entry.is_dir(),
                    }
                )
            return SafeToolResult(
                success=True,
                output={
                    "path": str(resolved),
                    "entries": entries,
                    "truncated": len(entries) >= limit,
                },
            )
        except Exception as exc:
            return SafeToolResult(success=False, error=str(exc))

    def read_file(self, path: str, *, max_bytes: int = 64_000) -> SafeToolResult:
        try:
            resolved = resolve_allowed_path(
                path, allowed_roots=self._allowed_roots, must_exist=True
            )
            if not resolved.is_file():
                return SafeToolResult(success=False, error="Path is not a file")
            size = resolved.stat().st_size
            if size > max_bytes:
                return SafeToolResult(
                    success=False,
                    error=f"File too large ({size} bytes; max {max_bytes})",
                )
            content = resolved.read_text(encoding="utf-8", errors="replace")
            return SafeToolResult(
                success=True,
                output={"path": str(resolved), "size": size, "content": content},
            )
        except Exception as exc:
            return SafeToolResult(success=False, error=str(exc))

    def ripgrep_search(
        self,
        pattern: str,
        path: str = ".",
        *,
        max_matches: int = 50,
    ) -> SafeToolResult:
        try:
            resolved = resolve_allowed_path(
                path, allowed_roots=self._allowed_roots, must_exist=True
            )
            regex = re.compile(pattern)
            matches: list[dict[str, str | int]] = []
            search_root = resolved if resolved.is_dir() else resolved.parent

            for root, dirnames, filenames in os.walk(search_root):
                dirnames[:] = [
                    d for d in dirnames if not d.startswith(".") and not d.startswith("_")
                ]
                for filename in filenames:
                    if filename.startswith("."):
                        continue
                    file_path = Path(root) / filename
                    try:
                        file_path.relative_to(resolved if resolved.is_dir() else resolved.parent)
                    except ValueError:
                        if resolved.is_file() and file_path != resolved:
                            continue
                    if resolved.is_file() and file_path != resolved:
                        continue
                    try:
                        resolve_allowed_path(str(file_path), allowed_roots=self._allowed_roots)
                    except PermissionError:
                        continue
                    try:
                        text = file_path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    for line_no, line in enumerate(text.splitlines(), start=1):
                        if regex.search(line):
                            matches.append(
                                {
                                    "path": str(file_path),
                                    "line": line_no,
                                    "text": line.strip()[:240],
                                }
                            )
                            if len(matches) >= max_matches:
                                return SafeToolResult(
                                    success=True,
                                    output={
                                        "pattern": pattern,
                                        "matches": matches,
                                        "truncated": True,
                                    },
                                )
            return SafeToolResult(
                success=True,
                output={"pattern": pattern, "matches": matches, "truncated": False},
            )
        except re.error as exc:
            return SafeToolResult(success=False, error=f"Invalid regex: {exc}")
        except Exception as exc:
            return SafeToolResult(success=False, error=str(exc))
