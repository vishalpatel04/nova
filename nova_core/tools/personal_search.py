"""Bounded read-only content search across approved personal folders."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nova_core.tools.search_scopes import (
    MAX_DISPLAY_MATCHES,
    MAX_FILES_SCANNED,
    MAX_SEARCH_DEPTH,
    is_probably_binary,
    resolve_all_approved_scopes,
    resolve_search_scope,
    should_skip_dir,
    should_skip_file,
)


@dataclass(frozen=True)
class PersonalSearchResult:
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None


class PersonalSearchTool:
    def __init__(self, *, search_roots: list[str] | None = None) -> None:
        self._search_roots = search_roots

    def search_scope(self, pattern: str, scope_path: str) -> PersonalSearchResult:
        validation = resolve_search_scope(scope_path, search_roots=self._search_roots)
        if not validation.allowed or validation.resolved is None:
            return PersonalSearchResult(success=False, error=validation.reason)
        return self._search_roots_internal(pattern, [validation.resolved])

    def search_all_approved(self, pattern: str) -> PersonalSearchResult:
        roots = resolve_all_approved_scopes(search_roots=self._search_roots)
        return self._search_roots_internal(pattern, roots)

    def _search_roots_internal(self, pattern: str, roots: list[Path]) -> PersonalSearchResult:
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return PersonalSearchResult(success=False, error=f"Invalid regex: {exc}")

        grouped: dict[str, list[dict[str, str | int]]] = defaultdict(list)
        files_scanned = 0
        truncated = False

        for root in roots:
            if not root.exists():
                continue
            for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                current = Path(dirpath)
                try:
                    depth = len(current.relative_to(root).parts)
                except ValueError:
                    depth = 0
                if depth > MAX_SEARCH_DEPTH:
                    dirnames.clear()
                    continue

                dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

                for filename in filenames:
                    if files_scanned >= MAX_FILES_SCANNED:
                        truncated = True
                        break
                    file_path = current / filename
                    if should_skip_file(file_path):
                        continue
                    if not self._file_in_roots(file_path, roots):
                        continue
                    if is_probably_binary(file_path):
                        continue
                    files_scanned += 1
                    try:
                        text = file_path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    rel = str(file_path)
                    for line_no, line in enumerate(text.splitlines(), start=1):
                        if regex.search(line):
                            grouped[rel].append(
                                {
                                    "line": line_no,
                                    "text": line.strip()[:240],
                                }
                            )
                            total = sum(len(v) for v in grouped.values())
                            if total >= MAX_DISPLAY_MATCHES:
                                truncated = True
                                break
                    if truncated:
                        break
                if truncated:
                    break
            if truncated:
                break

        flat_count = sum(len(v) for v in grouped.values())
        return PersonalSearchResult(
            success=True,
            output={
                "pattern": pattern,
                "match_count": flat_count,
                "file_count": len(grouped),
                "by_file": dict(grouped),
                "truncated": truncated,
                "files_scanned": files_scanned,
            },
        )

    @staticmethod
    def _file_in_roots(file_path: Path, roots: list[Path]) -> bool:
        resolved = file_path.resolve()
        for root in roots:
            try:
                resolved.relative_to(root.resolve())
                return True
            except ValueError:
                if resolved == root.resolve():
                    return True
        return False


def format_search_results(pattern: str, output: dict[str, Any]) -> str:
    match_count = int(output.get("match_count", 0))
    if match_count == 0:
        return f'Found 0 matches for "{pattern}".'

    lines = [f'Found {match_count} matches for "{pattern}".', ""]
    by_file = output.get("by_file") or {}
    shown = 0
    for path in sorted(by_file.keys()):
        entries = by_file[path]
        lines.append(f"{path} ({len(entries)} matches)")
        for entry in entries[:3]:
            lines.append(f"  L{entry['line']}: {entry['text']}")
        shown += len(entries)
        if shown >= MAX_DISPLAY_MATCHES:
            break
        lines.append("")

    if output.get("truncated"):
        lines.append(f"Showing first {MAX_DISPLAY_MATCHES} matches.")
    return "\n".join(lines).strip()
