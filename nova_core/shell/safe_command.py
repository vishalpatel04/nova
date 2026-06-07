"""Strict allowlist parser for approved shell commands."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from nova_core.tools.protected_paths import PROTECTED_PATH_MESSAGE, is_protected_path
from nova_core.tools.safe_paths import expand_allowed_roots, resolve_allowed_path

MAX_GIT_LOG_LINES = 20
MAX_FIND_DEPTH = 5

FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    ";",
    "&&",
    "||",
    "|",
    ">",
    ">>",
    "<",
    "$(",
    "`",
    "\n",
    "\r",
    "\\n",
)

FORBIDDEN_COMMANDS: frozenset[str] = frozenset(
    {
        "rm",
        "mv",
        "cp",
        "chmod",
        "chown",
        "sudo",
        "curl",
        "wget",
        "ssh",
        "scp",
        "nc",
        "python",
        "python3",
        "bash",
        "zsh",
        "sh",
        "eval",
        "env",
        "printenv",
        "export",
        "source",
        "open",
        "osascript",
        "launchctl",
        "docker",
        "brew",
        "npm",
        "pip",
        "pip3",
        "kill",
        "pkill",
        "killall",
        "nohup",
        "n8n",
    }
)

ALLOWED_MAKE_TARGETS: frozenset[str] = frozenset({"test", "lint", "typecheck"})

FIND_SAFE_FLAGS: frozenset[str] = frozenset({"-maxdepth", "-type", "-name"})


@dataclass(frozen=True)
class ShellValidationResult:
    allowed: bool
    blocked: bool = False
    reason: str | None = None
    argv: tuple[str, ...] | None = None
    cwd: Path | None = None
    command_preview: str = ""


def _default_cwd(allowed_roots: list[str] | None = None) -> Path:
    roots = expand_allowed_roots(allowed_roots)
    return roots[0]


def _contains_forbidden_syntax(raw: str) -> str | None:
    for token in FORBIDDEN_SUBSTRINGS:
        if token in raw:
            return f"Blocked: shell metacharacter or composition ({token!r}) is not allowed."
    if "$" in raw and "${" not in raw and "$(" not in raw and re.search(r"\$\w", raw):
        return "Blocked: variable expansion is not allowed."
    return None


def _resolve_safe_path(raw: str, *, allowed_roots: list[str] | None = None) -> Path:
    if is_protected_path(raw):
        raise PermissionError(PROTECTED_PATH_MESSAGE)
    path = resolve_allowed_path(raw, allowed_roots=allowed_roots, must_exist=False)
    if path.is_symlink():
        real = path.resolve()
        resolve_allowed_path(str(real), allowed_roots=allowed_roots, must_exist=False)
        return real
    return path


def _resolve_existing_file(raw: str, *, allowed_roots: list[str] | None = None) -> Path:
    path = _resolve_safe_path(raw, allowed_roots=allowed_roots)
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"Expected a file, got directory: {path}")
    real = path.resolve()
    _resolve_safe_path(str(real), allowed_roots=allowed_roots)
    return real


def validate_safe_shell_command(
    raw_command: str,
    *,
    allowed_roots: list[str] | None = None,
) -> ShellValidationResult:
    command = raw_command.strip()
    if not command:
        return ShellValidationResult(
            allowed=False, blocked=True, reason="Blocked: empty shell command."
        )

    syntax_block = _contains_forbidden_syntax(command)
    if syntax_block:
        return ShellValidationResult(allowed=False, blocked=True, reason=syntax_block)

    try:
        parts = shlex.split(command, posix=True)
    except ValueError as exc:
        return ShellValidationResult(
            allowed=False, blocked=True, reason=f"Blocked: invalid shell quoting ({exc})."
        )

    if not parts:
        return ShellValidationResult(
            allowed=False, blocked=True, reason="Blocked: empty shell command."
        )

    binary = parts[0].lower()
    if binary in FORBIDDEN_COMMANDS:
        return ShellValidationResult(
            allowed=False,
            blocked=True,
            reason=f"Blocked: command {binary!r} is not on the safe allowlist.",
        )

    cwd = _default_cwd(allowed_roots)

    try:
        argv = _build_argv(parts, allowed_roots=allowed_roots)
    except (PermissionError, FileNotFoundError, IsADirectoryError, ValueError) as exc:
        message = str(exc)
        if "protected" in message.lower() or "Blocked:" in message:
            return ShellValidationResult(allowed=False, blocked=True, reason=message)
        return ShellValidationResult(allowed=False, blocked=True, reason=f"Blocked: {message}")

    return ShellValidationResult(
        allowed=True,
        argv=tuple(argv),
        cwd=cwd,
        command_preview=command,
    )


def _build_argv(parts: list[str], *, allowed_roots: list[str] | None) -> list[str]:
    binary = parts[0].lower()
    args = parts[1:]

    if binary == "pwd":
        if args:
            raise ValueError("pwd accepts no arguments")
        return ["pwd"]

    if binary == "ls":
        argv = ["ls"]
        for arg in args:
            if arg.startswith("-"):
                if arg not in {"-l", "-a", "-la", "-al", "-1"}:
                    raise ValueError(f"ls flag not allowed: {arg}")
                argv.append(arg)
            else:
                path = _resolve_safe_path(arg, allowed_roots=allowed_roots)
                argv.append(str(path))
        return argv

    if binary == "find":
        if not args:
            raise ValueError("find requires a path")
        path_token = args[0]
        path = _resolve_safe_path(path_token, allowed_roots=allowed_roots)
        argv = ["find", str(path)]
        index = 1
        while index < len(args):
            flag = args[index]
            if flag not in FIND_SAFE_FLAGS:
                raise ValueError(f"find flag not allowed: {flag}")
            if flag == "-maxdepth":
                index += 1
                if index >= len(args):
                    raise ValueError("find -maxdepth requires a value")
                depth = int(args[index])
                if depth < 1 or depth > MAX_FIND_DEPTH:
                    raise ValueError(f"find -maxdepth must be 1..{MAX_FIND_DEPTH}")
                argv.extend([flag, str(depth)])
            elif flag in {"-type", "-name"}:
                index += 1
                if index >= len(args):
                    raise ValueError(f"find {flag} requires a value")
                argv.extend([flag, args[index]])
            index += 1
        return argv

    if binary in {"cat", "head", "tail"}:
        if not args:
            raise ValueError(f"{binary} requires a file path")
        file_args: list[str] = []
        index = 0
        argv = [binary]
        while index < len(args):
            arg = args[index]
            if arg == "-n" and binary in {"head", "tail"}:
                index += 1
                if index >= len(args):
                    raise ValueError(f"{binary} -n requires a value")
                count = int(args[index])
                if count < 1 or count > 200:
                    raise ValueError(f"{binary} -n must be 1..200")
                argv.extend(["-n", str(count)])
            elif arg.startswith("-"):
                raise ValueError(f"{binary} flag not allowed: {arg}")
            else:
                file_args.append(arg)
            index += 1
        if len(file_args) != 1:
            raise ValueError(f"{binary} accepts exactly one file path")
        path = _resolve_existing_file(file_args[0], allowed_roots=allowed_roots)
        argv.append(str(path))
        return argv

    if binary == "git":
        if not args:
            raise ValueError("git subcommand required")
        sub = args[0]
        if sub == "status":
            if len(args) > 1:
                raise ValueError("git status accepts no extra arguments")
            return ["git", "status"]
        if sub == "branch" and len(args) >= 2 and args[1] == "--show-current":
            if len(args) > 2:
                raise ValueError("git branch --show-current accepts no extra arguments")
            return ["git", "branch", "--show-current"]
        if sub == "diff" and len(args) >= 2 and args[1] == "--stat":
            if len(args) > 2:
                raise ValueError("git diff --stat accepts no path arguments in Phase 3F")
            return ["git", "diff", "--stat"]
        if sub == "log":
            if "--oneline" not in args[1:]:
                raise ValueError("git log requires --oneline")
            argv = ["git", "log", "--oneline"]
            count = MAX_GIT_LOG_LINES
            rest = args[1:]
            index = 0
            while index < len(rest):
                arg = rest[index]
                if arg == "--oneline":
                    index += 1
                    continue
                if arg in {"-n", "--max-count"}:
                    if index + 1 >= len(rest):
                        raise ValueError("git log count flag requires a value")
                    count = int(rest[index + 1])
                    index += 2
                    continue
                if arg.startswith("-"):
                    raise ValueError(f"git log flag not allowed: {arg}")
                index += 1
            count = min(max(count, 1), MAX_GIT_LOG_LINES)
            argv.extend(["-n", str(count)])
            return argv
        raise ValueError(f"git subcommand not allowed: {sub}")

    if binary == "make":
        if len(args) != 1:
            raise ValueError("make requires exactly one target")
        target = args[0]
        if target not in ALLOWED_MAKE_TARGETS:
            raise ValueError(f"make target not allowed: {target}")
        return ["make", target]

    raise ValueError(f"command not on safe allowlist: {binary}")


_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[a-zA-Z0-9]{8,}", re.I),
    re.compile(r"(?i)(api[_-]?key|secret|password|token|bearer)\s*[=:]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]+-----"),
)


def sanitize_output_excerpt(text: str, *, max_length: int = 4096) -> str:
    cleaned = text
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    if len(cleaned) > max_length:
        return cleaned[:max_length] + "\n… (truncated)"
    return cleaned
