"""Typed read-only worker command definitions."""

from enum import StrEnum


class WorkerCommandType(StrEnum):
    SYSTEM_STATUS = "system_status"
    HOSTNAME = "hostname"
    UPTIME = "uptime"
    OPERATING_SYSTEM_VERSION = "operating_system_version"
    CPU_ARCHITECTURE = "cpu_architecture"
    CONFIGURED_CAPABILITIES = "configured_capabilities"
    LIST_DIRECTORY = "list_directory"
    READ_FILE = "read_file"
    RIPGREP_SEARCH = "ripgrep_search"
    INSPECT_REPO = "inspect_repo"
    RUN_VALIDATION = "run_validation"
    READ_SAFE_FILE = "read_safe_file"
    APPLY_APPROVED_PATCH = "apply_approved_patch"


READ_ONLY_COMMAND_TYPES: frozenset[str] = frozenset(
    {
        WorkerCommandType.SYSTEM_STATUS.value,
        WorkerCommandType.HOSTNAME.value,
        WorkerCommandType.UPTIME.value,
        WorkerCommandType.OPERATING_SYSTEM_VERSION.value,
        WorkerCommandType.CPU_ARCHITECTURE.value,
        WorkerCommandType.CONFIGURED_CAPABILITIES.value,
        WorkerCommandType.LIST_DIRECTORY.value,
        WorkerCommandType.READ_FILE.value,
        WorkerCommandType.RIPGREP_SEARCH.value,
        WorkerCommandType.INSPECT_REPO.value,
        WorkerCommandType.RUN_VALIDATION.value,
        WorkerCommandType.READ_SAFE_FILE.value,
    }
)

PROJECT_COMMAND_TYPES: frozenset[str] = frozenset(
    {
        WorkerCommandType.INSPECT_REPO.value,
        WorkerCommandType.RUN_VALIDATION.value,
        WorkerCommandType.READ_SAFE_FILE.value,
        WorkerCommandType.APPLY_APPROVED_PATCH.value,
    }
)

MISSION_COMMAND_MAP: dict[str, str] = {
    "system_status": WorkerCommandType.SYSTEM_STATUS.value,
}
