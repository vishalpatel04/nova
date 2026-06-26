"""Resolve chat messages to capability actions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from nova_core.capabilities.model import CapabilityName, RiskLevel, risk_for_capability
from nova_core.shell.safe_command import validate_safe_shell_command
from nova_core.tools.protected_paths import PROTECTED_PATH_MESSAGE, is_protected_path


@dataclass(frozen=True)
class ActionResolution:
    kind: Literal["approval", "protected", "blocked"] = "approval"
    capability: CapabilityName | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    action_summary: str = ""
    preview: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    message: str | None = None


def _shell_command_preview(message: str) -> str:
    lowered = message.lower()
    for prefix in ("run shell ", "execute command ", "run "):
        if lowered.startswith(prefix):
            return message[len(prefix) :].strip() or message.strip()
    return message.strip()


def _extract_path_after(prefix: str, text: str) -> str:
    if text.lower().startswith(prefix.lower()):
        return text[len(prefix) :].strip()
    match = re.search(rf"{re.escape(prefix)}\s+(\S+)", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def resolve_chat_message(text: str) -> ActionResolution | None:
    lowered = text.lower().strip()

    if lowered.startswith("run shell ") or lowered.startswith("execute command "):
        command = _shell_command_preview(text)
        validation = validate_safe_shell_command(command)
        if not validation.allowed:
            return ActionResolution(
                kind="blocked",
                capability=CapabilityName.SHELL_EXECUTE,
                message=validation.reason or "Blocked: command is not on the safe shell allowlist.",
                action_summary="Execute shell command",
                preview=command,
                risk_level=RiskLevel.CRITICAL,
            )
        return ActionResolution(
            capability=CapabilityName.SHELL_EXECUTE,
            payload={"command": command},
            action_summary="Execute shell command",
            preview=command,
            risk_level=risk_for_capability(CapabilityName.SHELL_EXECUTE),
        )

    if "rm -rf" in lowered or lowered.startswith("sudo "):
        command = _shell_command_preview(text) if "shell" in lowered else text.strip()
        return ActionResolution(
            kind="blocked",
            capability=CapabilityName.SHELL_EXECUTE,
            message="Blocked: destructive or privileged commands cannot be approved.",
            action_summary="Execute destructive shell command",
            preview=command,
            risk_level=RiskLevel.CRITICAL,
        )

    if lowered.startswith("write file ") or "write file" in lowered:
        path = _extract_path_after("write file", text) or _extract_path_after("write", text)
        if path and is_protected_path(path):
            return ActionResolution(kind="protected", message=PROTECTED_PATH_MESSAGE)
        return ActionResolution(
            capability=CapabilityName.FILE_WRITE,
            payload={"path": path, "action": "write"},
            action_summary=f"Write file: {path or '(unspecified)'}",
            preview=path or text.strip(),
            risk_level=risk_for_capability(CapabilityName.FILE_WRITE),
        )

    if lowered.startswith("delete file ") or "delete file" in lowered:
        path = _extract_path_after("delete file", text)
        if path and is_protected_path(path):
            return ActionResolution(kind="protected", message=PROTECTED_PATH_MESSAGE)
        return ActionResolution(
            capability=CapabilityName.FILE_WRITE,
            payload={"path": path, "action": "delete"},
            action_summary=f"Delete file: {path or '(unspecified)'}",
            preview=path or text.strip(),
            risk_level=RiskLevel.HIGH,
        )

    if lowered.startswith("generate patch "):
        instruction = text[len("generate patch ") :].strip()
        return ActionResolution(
            capability=CapabilityName.CODE_PATCH,
            payload={"instruction": instruction},
            action_summary=f"Generate code patch: {instruction[:120]}",
            preview=instruction[:500],
            risk_level=risk_for_capability(CapabilityName.CODE_PATCH),
        )

    if "git commit" in lowered:
        return ActionResolution(
            capability=CapabilityName.GIT_COMMIT,
            payload={"command": text.strip()},
            action_summary="Create git commit",
            preview=text.strip()[:500],
            risk_level=risk_for_capability(CapabilityName.GIT_COMMIT),
        )

    if "git push" in lowered:
        return ActionResolution(
            kind="blocked",
            capability=CapabilityName.GIT_PUSH,
            message="Blocked: git push requires additional safeguards and is not enabled yet.",
            action_summary="Git push",
            preview=text.strip()[:500],
            risk_level=RiskLevel.CRITICAL,
        )

    if "open browser" in lowered or "control browser" in lowered or "browser automation" in lowered:
        return ActionResolution(
            kind="blocked",
            capability=CapabilityName.BROWSER_CONTROL,
            message="Blocked: browser control is not enabled yet.",
            action_summary="Browser control",
            preview=text.strip()[:500],
            risk_level=RiskLevel.CRITICAL,
        )

    if "run n8n" in lowered or "openclaw" in lowered or "control desktop" in lowered:
        return ActionResolution(
            kind="blocked",
            capability=CapabilityName.AUTOMATION_RUN,
            message="Blocked: automation execution is scaffold-only and not enabled yet.",
            action_summary="Run automation",
            preview=text.strip()[:500],
            risk_level=RiskLevel.CRITICAL,
        )

    if "send email" in lowered and "draft" not in lowered and "investor update" not in lowered:
        return ActionResolution(
            kind="blocked",
            capability=CapabilityName.AUTOMATION_RUN,
            message="Blocked: use draft flow first, then approve sending explicitly.",
            action_summary="Send email",
            preview=text.strip()[:500],
            risk_level=RiskLevel.HIGH,
        )

    return None


def cloud_file_resolution(path: str) -> ActionResolution:
    if is_protected_path(path):
        return ActionResolution(kind="protected", message=PROTECTED_PATH_MESSAGE)
    return ActionResolution(
        capability=CapabilityName.CLOUD_SEND_FILE,
        payload={"path": path, "action": "read_transmit"},
        action_summary=f"Send file contents to cloud provider: {path}",
        preview=path,
        risk_level=risk_for_capability(CapabilityName.CLOUD_SEND_FILE),
    )
