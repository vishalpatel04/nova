"""NOVA workspace paths and write guards."""

from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_WORKSPACE_ROOT = Path.home() / "Projects" / "nova-workspace"
RUNS_DIR_NAME = ".nova-runs"
CALCULATOR_APP_DIR = "calculator-app"

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*\S+"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._-]+"),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
)


def workspace_root() -> Path:
    override = os.environ.get("NOVA_WORKSPACE_ROOT", "").strip()
    if override:
        return Path(os.path.expanduser(override)).resolve()
    return DEFAULT_WORKSPACE_ROOT.resolve()


def runs_dir() -> Path:
    path = workspace_root() / RUNS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def calculator_project_path() -> Path:
    return workspace_root() / CALCULATOR_APP_DIR


def is_within_workspace(path: Path | str) -> bool:
    candidate = Path(os.path.expanduser(str(path))).resolve()
    root = workspace_root()
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return candidate == root


def assert_workspace_write(path: Path | str) -> Path:
    resolved = Path(os.path.expanduser(str(path))).resolve()
    if not is_within_workspace(resolved):
        raise PermissionError(
            f"Write blocked: {resolved} is outside NOVA workspace {workspace_root()}"
        )
    return resolved


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted
