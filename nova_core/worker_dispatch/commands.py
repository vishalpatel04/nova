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


READ_ONLY_COMMAND_TYPES: frozenset[str] = frozenset(WorkerCommandType)

MISSION_COMMAND_MAP: dict[str, str] = {
    "system_status": WorkerCommandType.SYSTEM_STATUS.value,
}
