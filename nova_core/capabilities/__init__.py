"""NOVA capability model for tool permission gates."""

from nova_core.capabilities.model import (
    APPROVAL_REQUIRED_CAPABILITIES,
    PERMANENTLY_BLOCKED_CAPABILITIES,
    ActionApprovalStatus,
    CapabilityName,
    RiskLevel,
    compute_action_fingerprint,
    default_allowed,
    risk_for_capability,
)
from nova_core.capabilities.resolver import ActionResolution, resolve_chat_message

__all__ = [
    "APPROVAL_REQUIRED_CAPABILITIES",
    "ActionApprovalStatus",
    "ActionResolution",
    "CapabilityName",
    "PERMANENTLY_BLOCKED_CAPABILITIES",
    "RiskLevel",
    "compute_action_fingerprint",
    "default_allowed",
    "resolve_chat_message",
    "risk_for_capability",
]
