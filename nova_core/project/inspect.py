"""Safe repository inspection within project root."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from nova_core.shell.executor import execute_safe_command
from nova_core.shell.safe_command import validate_safe_shell_command


@dataclass
class RepoInspection:
    project_root: str
    project_name: str
    git_status: str = ""
    current_branch: str = ""
    recent_commits: str = ""
    file_tree: str = ""
    readme_excerpt: str = ""
    detected_commands: dict[str, str] = field(default_factory=dict)
    tooling: dict[str, bool] = field(default_factory=dict)


def _bounded_tree(root: Path, *, max_depth: int = 2, max_entries: int = 80) -> str:
    lines: list[str] = []
    count = 0
    skip = {".git", "node_modules", ".venv", "DerivedData", "dist", "build", "__pycache__"}

    def walk(path: Path, depth: int, prefix: str) -> None:
        nonlocal count
        if depth > max_depth or count >= max_entries:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        for entry in entries:
            if entry.name in skip or entry.name.startswith("."):
                continue
            count += 1
            if count > max_entries:
                lines.append(f"{prefix}… (truncated)")
                return
            marker = "📁" if entry.is_dir() else "📄"
            lines.append(f"{prefix}{marker} {entry.name}")
            if entry.is_dir() and depth < max_depth:
                walk(entry, depth + 1, prefix + "  ")

    walk(root, 0, "")
    return "\n".join(lines) if lines else "(empty)"


def _detect_tooling(root: Path) -> dict[str, bool]:
    return {
        "python": (root / "pyproject.toml").exists() or (root / "requirements.txt").exists(),
        "makefile": (root / "Makefile").exists(),
        "ios": (root / "apps" / "ios").exists(),
        "docs": (root / "docs").exists(),
        "tests": (root / "tests").exists(),
    }


def _detect_commands(root: Path) -> dict[str, str]:
    cmds: dict[str, str] = {}
    if (root / "Makefile").exists():
        cmds["test"] = "make test"
        cmds["lint"] = "make lint"
        cmds["typecheck"] = "make typecheck"
    return cmds


def normalize_git_branch(project_root: Path, stdout: str) -> str | None:
    """Return branch name, None if not a git repo, or 'uninitialized' if no commits."""
    text = stdout.strip()
    if text.lower().startswith("fatal:") or "not a git repository" in text.lower():
        return None
    if not (project_root / ".git").exists():
        return None
    if not text:
        return "uninitialized"
    return text


async def _run_git(project_root: Path, subcommand: str) -> str:
    command = f"git {subcommand}"
    validation = validate_safe_shell_command(
        command,
        allowed_roots=[str(project_root)],
    )
    if not validation.allowed:
        return ""
    result = await execute_safe_command(validation, cwd=project_root)
    if result.timed_out or result.blocked:
        return ""
    return (result.stdout_excerpt or "").strip()


async def inspect_repo(project_root: Path) -> RepoInspection:
    root = project_root.resolve()
    name = root.name
    tooling = _detect_tooling(root)
    readme = ""
    readme_path = root / "README.md"
    if readme_path.is_file() and readme_path.stat().st_size < 32_000:
        readme = readme_path.read_text(encoding="utf-8", errors="replace")[:1500]

    git_status, branch_out, log = await asyncio.gather(
        _run_git(root, "status"),
        _run_git(root, "branch --show-current"),
        _run_git(root, "log --oneline -n 10"),
    )
    branch = normalize_git_branch(root, branch_out)

    return RepoInspection(
        project_root=str(root),
        project_name=name,
        git_status=git_status or "(no git or empty)",
        current_branch=branch or "",
        recent_commits=log or "(no commits)",
        file_tree=_bounded_tree(root),
        readme_excerpt=readme,
        detected_commands=_detect_commands(root),
        tooling=tooling,
    )


def format_inspection(inspection: RepoInspection) -> str:
    cmds = ", ".join(f"{k}={v}" for k, v in inspection.detected_commands.items()) or "none"
    tooling = ", ".join(k for k, v in inspection.tooling.items() if v) or "none"
    return (
        f"Project: {inspection.project_name}\n"
        f"Root: {inspection.project_root}\n"
        f"Branch: {inspection.current_branch or '(no git)'}\n\n"
        f"Git status:\n{inspection.git_status}\n\n"
        f"Recent commits:\n{inspection.recent_commits}\n\n"
        f"File tree:\n{inspection.file_tree}\n\n"
        f"Tooling: {tooling}\n"
        f"Validation commands: {cmds}\n\n"
        f"README excerpt:\n{inspection.readme_excerpt[:800]}"
    )
