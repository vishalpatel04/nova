"""Run safe validation commands within active project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nova_core.shell.executor import DEFAULT_TIMEOUT_SECONDS, execute_safe_command
from nova_core.shell.safe_command import validate_safe_shell_command


@dataclass(frozen=True)
class ValidationResult:
    command: str
    exit_code: int
    stdout_excerpt: str
    stderr_excerpt: str
    blocked: bool = False
    block_reason: str | None = None


async def run_validation_command(
    project_root: Path,
    command: str,
    *,
    allowed_roots: list[str] | None = None,
) -> ValidationResult:
    roots = allowed_roots or [str(project_root)]
    validation = validate_safe_shell_command(command, allowed_roots=roots)
    if not validation.allowed:
        return ValidationResult(
            command=command,
            exit_code=-1,
            stdout_excerpt="",
            stderr_excerpt=validation.reason or "Command blocked",
            blocked=True,
            block_reason=validation.reason,
        )
    result = await execute_safe_command(
        validation, cwd=project_root, timeout_seconds=DEFAULT_TIMEOUT_SECONDS
    )
    if result.blocked:
        return ValidationResult(
            command=command,
            exit_code=-1,
            stdout_excerpt="",
            stderr_excerpt=result.block_reason or "Blocked",
            blocked=True,
            block_reason=result.block_reason,
        )
    return ValidationResult(
        command=command,
        exit_code=result.exit_code,
        stdout_excerpt=result.stdout_excerpt,
        stderr_excerpt=result.stderr_excerpt,
        blocked=result.timed_out,
        block_reason="Timed out" if result.timed_out else None,
    )


def pick_validation_command(project_root: Path) -> str | None:
    if (project_root / "Makefile").exists():
        return "make test"
    if (project_root / "pyproject.toml").exists():
        return "make test"
    return None
