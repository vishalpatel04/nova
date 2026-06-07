"""Execute validated safe shell commands with timeout and output bounds."""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass
from pathlib import Path

from nova_core.shell.safe_command import ShellValidationResult, sanitize_output_excerpt

DEFAULT_TIMEOUT_SECONDS = 10
OUTPUT_EXCERPT_LIMIT = 4096


@dataclass(frozen=True)
class ShellExecutionResult:
    exit_code: int
    stdout_excerpt: str
    stderr_excerpt: str
    timed_out: bool
    blocked: bool = False
    block_reason: str | None = None


def _minimal_env() -> dict[str, str]:
    path = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    home = str(Path.home())
    return {
        "PATH": path,
        "HOME": home,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


async def execute_safe_command(
    validation: ShellValidationResult,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    cwd: Path | None = None,
) -> ShellExecutionResult:
    if not validation.allowed or validation.argv is None:
        return ShellExecutionResult(
            exit_code=-1,
            stdout_excerpt="",
            stderr_excerpt=validation.reason or "Command blocked",
            timed_out=False,
            blocked=True,
            block_reason=validation.reason,
        )

    workdir = cwd or validation.cwd
    if workdir is None:
        return ShellExecutionResult(
            exit_code=-1,
            stdout_excerpt="",
            stderr_excerpt="Missing working directory",
            timed_out=False,
            blocked=True,
        )

    proc = await asyncio.create_subprocess_exec(
        *validation.argv,
        cwd=str(workdir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_minimal_env(),
        start_new_session=True,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            proc.kill()
        await proc.wait()
        return ShellExecutionResult(
            exit_code=-1,
            stdout_excerpt="",
            stderr_excerpt=f"Command timed out after {timeout_seconds}s",
            timed_out=True,
        )

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return ShellExecutionResult(
        exit_code=int(proc.returncode or 0),
        stdout_excerpt=sanitize_output_excerpt(stdout, max_length=OUTPUT_EXCERPT_LIMIT),
        stderr_excerpt=sanitize_output_excerpt(stderr, max_length=OUTPUT_EXCERPT_LIMIT),
        timed_out=False,
    )
