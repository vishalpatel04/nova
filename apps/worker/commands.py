"""Typed read-only worker command handlers — no shell execution."""

import platform
from typing import Any

from apps.worker.capabilities import capability_report, detect_capabilities
from nova_core.tools.safe_readonly import SafeReadonlyTools
from nova_core.worker_dispatch.commands import WorkerCommandType

_safe_tools = SafeReadonlyTools()


def _uptime_seconds() -> int:
    try:
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_utime)
    except Exception:
        return 0


def execute_read_only_command(
    command_type: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = payload or {}
    if command_type not in {c.value for c in WorkerCommandType}:
        raise ValueError(f"Unsupported command type: {command_type}")

    if command_type == WorkerCommandType.LIST_DIRECTORY.value:
        result = _safe_tools.list_directory(str(payload.get("path", ".")))
        return {"success": result.success, "output": result.output, "error": result.error}
    if command_type == WorkerCommandType.READ_FILE.value:
        result = _safe_tools.read_file(str(payload.get("path", "")))
        return {"success": result.success, "output": result.output, "error": result.error}
    if command_type == WorkerCommandType.RIPGREP_SEARCH.value:
        result = _safe_tools.ripgrep_search(
            str(payload.get("pattern", "")),
            str(payload.get("path", ".")),
        )
        return {"success": result.success, "output": result.output, "error": result.error}

    if command_type == WorkerCommandType.SYSTEM_STATUS.value:
        report = capability_report()
        return {
            "hostname": platform.node(),
            "os_version": platform.platform(),
            "architecture": platform.machine(),
            "uptime_seconds": _uptime_seconds(),
            "capabilities": report["capabilities"],
            "dangerous_tools_enabled": False,
            "status": "ok",
        }
    if command_type == WorkerCommandType.HOSTNAME.value:
        return {"hostname": platform.node()}
    if command_type == WorkerCommandType.UPTIME.value:
        return {"uptime_seconds": _uptime_seconds()}
    if command_type == WorkerCommandType.OPERATING_SYSTEM_VERSION.value:
        return {"os_version": platform.platform()}
    if command_type == WorkerCommandType.CPU_ARCHITECTURE.value:
        return {"architecture": platform.machine()}
    if command_type == WorkerCommandType.CONFIGURED_CAPABILITIES.value:
        return capability_report()

    return {"capabilities": detect_capabilities()}
