"""Capability names, defaults, and action fingerprinting."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any


class CapabilityName(StrEnum):
    FILE_READ = "file.read"
    FILE_WRITE = "file.write"
    SHELL_PREVIEW = "shell.preview"
    SHELL_EXECUTE = "shell.execute"
    CLOUD_SEND_FILE = "cloud.send_file"
    AUTOMATION_RUN = "automation.run"
    BROWSER_CONTROL = "browser.control"
    CODE_PATCH = "code.patch"
    GIT_COMMIT = "git.commit"
    GIT_PUSH = "git.push"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


DEFAULT_ALLOWED: frozenset[CapabilityName] = frozenset(
    {CapabilityName.FILE_READ, CapabilityName.SHELL_PREVIEW}
)

APPROVAL_REQUIRED_CAPABILITIES: frozenset[CapabilityName] = frozenset(
    {
        CapabilityName.FILE_WRITE,
        CapabilityName.SHELL_EXECUTE,
        CapabilityName.CODE_PATCH,
        CapabilityName.CLOUD_SEND_FILE,
        CapabilityName.GIT_COMMIT,
    }
)

PERMANENTLY_BLOCKED_CAPABILITIES: frozenset[CapabilityName] = frozenset(
    {
        CapabilityName.AUTOMATION_RUN,
        CapabilityName.BROWSER_CONTROL,
        CapabilityName.GIT_PUSH,
    }
)

_RISK_BY_CAPABILITY: dict[CapabilityName, RiskLevel] = {
    CapabilityName.FILE_READ: RiskLevel.LOW,
    CapabilityName.FILE_WRITE: RiskLevel.HIGH,
    CapabilityName.SHELL_PREVIEW: RiskLevel.LOW,
    CapabilityName.SHELL_EXECUTE: RiskLevel.CRITICAL,
    CapabilityName.CLOUD_SEND_FILE: RiskLevel.HIGH,
    CapabilityName.AUTOMATION_RUN: RiskLevel.CRITICAL,
    CapabilityName.BROWSER_CONTROL: RiskLevel.CRITICAL,
    CapabilityName.CODE_PATCH: RiskLevel.HIGH,
    CapabilityName.GIT_COMMIT: RiskLevel.MEDIUM,
    CapabilityName.GIT_PUSH: RiskLevel.CRITICAL,
}


def default_allowed(capability: CapabilityName) -> bool:
    return capability in DEFAULT_ALLOWED


def risk_for_capability(capability: CapabilityName) -> RiskLevel:
    return _RISK_BY_CAPABILITY.get(capability, RiskLevel.MEDIUM)


def compute_action_fingerprint(capability: str, payload: dict[str, Any]) -> str:
    normalized = json.dumps({"capability": capability, "payload": payload}, sort_keys=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
