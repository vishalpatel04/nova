"""Safe Forge execution helpers — prompts, redaction, workspace bounds."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from nova_core.agent_os.workspace import redact_secrets, workspace_root
from nova_core.forge.engines.base import ForgeConstraints, ForgeTask

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
)


def is_path_allowed(path: Path, constraints: ForgeConstraints) -> bool:
    resolved = path.resolve()
    workspace = constraints.workspace.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        return False
    text = str(resolved)
    return not any(forbidden in text for forbidden in constraints.forbidden_patterns)


def redact_prompt_text(text: str) -> str:
    cleaned = redact_secrets(text)
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


def write_engine_prompt(
    evidence_dir: Path,
    *,
    engine_id: str,
    task: ForgeTask,
    constraints: ForgeConstraints,
) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"{engine_id}_prompt.txt"
    body = "\n".join(
        [
            f"# NOVA Forge prompt — {engine_id}",
            "",
            "## User request",
            redact_prompt_text(task.request),
            "",
            "## App spec",
            redact_prompt_text(task.app_spec_summary or "(none)"),
            "",
            "## Acceptance criteria",
            *[f"- {item}" for item in task.acceptance_criteria],
            "",
            "## Allowed workspace",
            str(constraints.workspace.resolve()),
            "",
            "## Forbidden paths",
            *[f"- {item}" for item in constraints.forbidden_patterns],
            "",
            "## Safety rules",
            "- Do not read NOVA_VAULT, .env, or SSH keys",
            "- Do not git commit/push/deploy without approval",
            "- Stay inside approved workspace",
            "",
            f"## Validation command\n{task.validation_command}",
            "",
            "## Expected output",
            "- Working code in workspace with evidence log",
        ]
    )
    path.write_text(body, encoding="utf-8")
    return path


def run_safe_command(
    command: list[str],
    *,
    cwd: Path,
    constraints: ForgeConstraints,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    if not is_path_allowed(cwd, constraints):
        return 1, "", "workspace boundary violation"
    import os

    merged = {**os.environ, **(env or {})}
    for key in list(merged.keys()):
        if (
            "KEY" in key.upper() or "SECRET" in key.upper() or "TOKEN" in key.upper()
        ) and key not in {"PATH", "HOME"}:
            merged[key] = "[REDACTED_FOR_FORGE]"
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=constraints.timeout_seconds,
            env=merged,
            check=False,
        )
        return proc.returncode, redact_secrets(proc.stdout), redact_secrets(proc.stderr)
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"
    except OSError as exc:
        return 1, "", str(exc)


def default_constraints(project_path: Path | None = None) -> ForgeConstraints:
    ws = project_path or workspace_root()
    return ForgeConstraints(workspace=ws)
