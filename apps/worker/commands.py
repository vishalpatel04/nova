"""Worker command handlers — read-only plus approved patch apply with revalidation."""

from __future__ import annotations

import asyncio
import platform
from pathlib import Path
from typing import Any

from apps.worker.capabilities import capability_report, detect_capabilities
from nova_core.patch.apply import apply_patch_payload
from nova_core.patch.policy import validate_patch_payload
from nova_core.project.context import validate_project_root
from nova_core.project.inspect import format_inspection, inspect_repo
from nova_core.project.validation import pick_validation_command, run_validation_command
from nova_core.tools.safe_readonly import SafeReadonlyTools
from nova_core.worker_dispatch.commands import WorkerCommandType

_safe_tools = SafeReadonlyTools()


def _uptime_seconds() -> int:
    try:
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_utime)
    except Exception:
        return 0


def _run_async(coro: Any) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    if loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def execute_read_only_command(
    command_type: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = payload or {}
    allowed = {c.value for c in WorkerCommandType}
    if command_type not in allowed:
        raise ValueError(f"Unsupported command type: {command_type}")

    if command_type == WorkerCommandType.INSPECT_REPO.value:
        root_raw = str(payload.get("project_root", ""))
        validation = validate_project_root(root_raw)
        if not validation.allowed or validation.resolved is None:
            return {"success": False, "error": validation.reason}
        inspection = _run_async(inspect_repo(validation.resolved))
        return {
            "success": True,
            "output": format_inspection(inspection),
            "project_root": str(validation.resolved),
        }

    if command_type == WorkerCommandType.RUN_VALIDATION.value:
        root_raw = str(payload.get("project_root", ""))
        validation = validate_project_root(root_raw)
        if not validation.allowed or validation.resolved is None:
            return {"success": False, "error": validation.reason}
        cmd = (
            str(payload.get("command", ""))
            or pick_validation_command(validation.resolved)
            or "make test"
        )
        result = _run_async(run_validation_command(validation.resolved, cmd))
        return {
            "success": not result.blocked,
            "command": cmd,
            "exit_code": result.exit_code,
            "stdout": result.stdout_excerpt,
            "stderr": result.stderr_excerpt,
            "error": result.block_reason,
        }

    if command_type == WorkerCommandType.READ_SAFE_FILE.value:
        path = str(payload.get("path", ""))
        if validate_project_root(str(Path(path).parent)).allowed is False:
            result = _safe_tools.read_file(path)
        else:
            result = _safe_tools.read_file(path)
        return {"success": result.success, "output": result.output, "error": result.error}

    if command_type == WorkerCommandType.APPLY_APPROVED_PATCH.value:
        root_raw = str(payload.get("project_root", ""))
        patch_payload = payload.get("patch_payload") or {}
        root_validation = validate_project_root(root_raw)
        if not root_validation.allowed or root_validation.resolved is None:
            return {"success": False, "error": root_validation.reason}
        patch_validation = validate_patch_payload(root_validation.resolved, patch_payload)
        if not patch_validation.allowed:
            return {"success": False, "error": patch_validation.reason}
        apply_result = apply_patch_payload(root_validation.resolved, patch_validation)
        return {
            "success": apply_result.success,
            "applied_files": list(apply_result.applied_files),
            "error": apply_result.error,
        }

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
