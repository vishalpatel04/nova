"""Provider-aware file content transmission rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from nova_core.providers.router import ProviderName
from nova_core.tools.protected_paths import PROTECTED_PATH_MESSAGE, is_protected_path


class FileTransmissionDecision(StrEnum):
    ALLOW = "allow"
    BLOCK_PROTECTED = "block_protected"
    BLOCK_CLOUD_APPROVAL = "block_cloud_approval"


@dataclass(frozen=True)
class FileTransmissionEvaluation:
    decision: FileTransmissionDecision
    message: str | None = None


CLOUD_PROVIDERS: frozenset[ProviderName] = frozenset({ProviderName.OPENAI, ProviderName.ANTHROPIC})

LOCAL_PROVIDERS: frozenset[ProviderName] = frozenset(
    {ProviderName.LOCAL, ProviderName.QWEN, ProviderName.DEEPSEEK}
)


def is_cloud_provider(provider: ProviderName) -> bool:
    return provider in CLOUD_PROVIDERS


def is_local_provider(provider: ProviderName) -> bool:
    return provider in LOCAL_PROVIDERS


def evaluate_file_transmission(
    provider: ProviderName,
    path: str,
    *,
    approved: bool = False,
) -> FileTransmissionEvaluation:
    if is_protected_path(path):
        return FileTransmissionEvaluation(
            decision=FileTransmissionDecision.BLOCK_PROTECTED,
            message=PROTECTED_PATH_MESSAGE,
        )
    if is_cloud_provider(provider) and not approved:
        return FileTransmissionEvaluation(
            decision=FileTransmissionDecision.BLOCK_CLOUD_APPROVAL,
            message=(
                "Blocked: sending file contents to a cloud provider requires explicit approval."
            ),
        )
    return FileTransmissionEvaluation(decision=FileTransmissionDecision.ALLOW)


def scrub_runtime_detail(detail: str | None) -> str | None:
    """Remove values that could resemble secrets from runtime status details."""
    if not detail:
        return detail
    lowered = detail.lower()
    secret_markers = ("sk-", "api_key", "secret", "password", "token=", "bearer ", "x-api-key")
    if any(marker in lowered for marker in secret_markers):
        return "redacted"
    return detail
