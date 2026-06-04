"""Approval-gated code assistance tools without autonomous shell execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nova_core.tools.safe_paths import resolve_allowed_path
from nova_core.tools.safe_readonly import SafeReadonlyTools


@dataclass(frozen=True)
class CodeToolResult:
    success: bool
    output: dict[str, Any]
    requires_approval: bool = False
    error: str | None = None


class CodeRuntime:
    def __init__(self, allowed_roots: list[str] | None = None) -> None:
        self.safe_tools = SafeReadonlyTools(allowed_roots=allowed_roots)
        self.allowed_roots = allowed_roots

    def repo_analysis(self, path: str = "~/Projects/nova") -> CodeToolResult:
        resolved = resolve_allowed_path(path, allowed_roots=self.allowed_roots, must_exist=True)
        files = self.safe_tools.list_directory(str(resolved))
        if not files.success:
            return CodeToolResult(False, {}, error=files.error)
        output = files.output
        assert isinstance(output, dict)
        entries = output.get("entries", [])
        names = [str(entry.get("name")) for entry in entries]
        return CodeToolResult(
            True,
            {
                "repo": str(resolved),
                "signals": {
                    "python": "pyproject.toml" in names,
                    "ios": "apps" in names,
                    "docs": "docs" in names,
                    "tests": "tests" in names,
                },
                "top_level": names[:40],
            },
        )

    def explain_code(self, path: str) -> CodeToolResult:
        read = self.safe_tools.read_file(path)
        if not read.success:
            return CodeToolResult(False, {}, error=read.error)
        output = read.output
        assert isinstance(output, dict)
        content = str(output.get("content", ""))
        lines = content.splitlines()
        return CodeToolResult(
            True,
            {
                "path": output.get("path"),
                "summary": self._summarize(lines),
                "line_count": len(lines),
            },
        )

    def diff_review(self, diff_text: str) -> CodeToolResult:
        risky = [
            marker
            for marker in ("rm -rf", "subprocess", "shell=True", "OPENAI_API_KEY", ".env")
            if marker in diff_text
        ]
        return CodeToolResult(
            True,
            {
                "risk_markers": risky,
                "line_count": len(diff_text.splitlines()),
                "review": "No high-risk markers found." if not risky else "Review required.",
            },
        )

    def patch_plan(self, instruction: str, path: str = "~/Projects/nova") -> CodeToolResult:
        resolved = resolve_allowed_path(path, allowed_roots=self.allowed_roots, must_exist=True)
        return CodeToolResult(
            True,
            {
                "repo": str(resolved),
                "instruction": instruction,
                "plan": [
                    "inspect relevant files",
                    "produce a patch for human review",
                    "run tests after explicit approval",
                ],
            },
            requires_approval=True,
        )

    def _summarize(self, lines: list[str]) -> str:
        non_empty = [line.strip() for line in lines if line.strip()]
        if not non_empty:
            return "Empty file."
        first = non_empty[0]
        if first.startswith('"""') or first.startswith("import ") or first.startswith("from "):
            return f"Starts with `{first[:100]}` and contains {len(non_empty)} non-empty lines."
        path_like = Path(first)
        if path_like.suffix:
            return f"Looks like source or config content beginning with `{first[:100]}`."
        return f"Begins with `{first[:100]}` and contains {len(non_empty)} non-empty lines."
