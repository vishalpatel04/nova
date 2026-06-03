"""Worker capability detection — reports available tools without executing them."""

import shutil
from typing import Any

from nova_core.models.enums import DeviceCapability

ALL_CAPABILITIES = [c.value for c in DeviceCapability]


def detect_capabilities() -> list[str]:
    """Detect which capabilities are available on this node."""
    available: list[str] = []

    checks: dict[str, bool] = {
        DeviceCapability.SHELL.value: shutil.which("bash") is not None,
        DeviceCapability.FILESYSTEM.value: True,
        DeviceCapability.SPOTLIGHT.value: shutil.which("mdfind") is not None,
        DeviceCapability.RIPGREP.value: shutil.which("rg") is not None,
        DeviceCapability.GIT.value: shutil.which("git") is not None,
        DeviceCapability.GITHUB_CLI.value: shutil.which("gh") is not None,
        DeviceCapability.CODEX.value: shutil.which("codex") is not None,
        DeviceCapability.CURSOR.value: shutil.which("cursor") is not None,
        DeviceCapability.OLLAMA.value: shutil.which("ollama") is not None,
        DeviceCapability.BROWSER.value: True,
        DeviceCapability.APPLESCRIPT.value: shutil.which("osascript") is not None,
        DeviceCapability.SCREENSHOT.value: shutil.which("screencapture") is not None,
        DeviceCapability.DESKTOP_AUTOMATION.value: False,
        DeviceCapability.PPT_RENDER.value: False,
    }

    for cap, present in checks.items():
        if present:
            available.append(cap)

    return available


def capability_report() -> dict[str, Any]:
    caps = detect_capabilities()
    return {
        "capabilities": caps,
        "total_defined": len(ALL_CAPABILITIES),
        "total_available": len(caps),
        "dangerous_enabled": False,
    }
