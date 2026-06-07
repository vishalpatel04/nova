"""Provider trust lanes — local vs external restricted."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from nova_core.models.enums import ProviderLane
from nova_core.schemas.settings import Settings
from nova_core.tools.protected_paths import is_protected_path


class ExternalProviderKind(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    CODEX_CLI = "codex_cli"


@dataclass(frozen=True)
class ProviderStatus:
    kind: str
    configured: bool
    enabled: bool
    lane: str


@dataclass(frozen=True)
class TrustLaneDecision:
    allowed: bool
    lane: str
    reason: str | None = None
    requires_approval: bool = False


def active_lane(settings: Settings) -> ProviderLane:
    if settings.nova_external_providers_enabled:
        return ProviderLane.EXTERNAL_RESTRICTED
    return ProviderLane.LOCAL


def external_provider_status(settings: Settings) -> list[ProviderStatus]:
    """Runtime status — configured true/false only, never raw keys."""
    return [
        ProviderStatus(
            kind=ExternalProviderKind.ANTHROPIC.value,
            configured=bool(settings.nova_anthropic_api_key),
            enabled=settings.nova_external_providers_enabled and settings.nova_anthropic_enabled,
            lane=ProviderLane.EXTERNAL_RESTRICTED.value,
        ),
        ProviderStatus(
            kind=ExternalProviderKind.OPENAI.value,
            configured=bool(settings.nova_openai_api_key),
            enabled=settings.nova_external_providers_enabled and settings.nova_openai_enabled,
            lane=ProviderLane.EXTERNAL_RESTRICTED.value,
        ),
        ProviderStatus(
            kind=ExternalProviderKind.CODEX_CLI.value,
            configured=False,
            enabled=settings.nova_external_providers_enabled and settings.nova_codex_cli_enabled,
            lane=ProviderLane.EXTERNAL_RESTRICTED.value,
        ),
    ]


def evaluate_external_call(
    settings: Settings,
    *,
    provider: ExternalProviderKind,
    file_paths: list[str] | None = None,
    cloud_send_approved: bool = False,
) -> TrustLaneDecision:
    if not settings.nova_external_providers_enabled:
        return TrustLaneDecision(
            allowed=False,
            lane=ProviderLane.EXTERNAL_RESTRICTED.value,
            reason="External providers disabled (NOVA_EXTERNAL_PROVIDERS_ENABLED=false)",
        )
    enabled_map = {
        ExternalProviderKind.ANTHROPIC: settings.nova_anthropic_enabled,
        ExternalProviderKind.OPENAI: settings.nova_openai_enabled,
        ExternalProviderKind.CODEX_CLI: settings.nova_codex_cli_enabled,
    }
    if not enabled_map.get(provider, False):
        return TrustLaneDecision(
            allowed=False,
            lane=ProviderLane.EXTERNAL_RESTRICTED.value,
            reason=f"Provider {provider.value} not enabled",
        )
    if file_paths:
        for path in file_paths:
            if is_protected_path(path):
                return TrustLaneDecision(
                    allowed=False,
                    lane=ProviderLane.EXTERNAL_RESTRICTED.value,
                    reason="Protected content cannot be sent externally",
                )
        if not cloud_send_approved:
            return TrustLaneDecision(
                allowed=False,
                lane=ProviderLane.EXTERNAL_RESTRICTED.value,
                reason="cloud.send_file approval required",
                requires_approval=True,
            )
    return TrustLaneDecision(
        allowed=True,
        lane=ProviderLane.EXTERNAL_RESTRICTED.value,
    )


def trust_lane_summary(settings: Settings) -> dict[str, Any]:
    lane = active_lane(settings)
    return {
        "active_lane": lane.value,
        "local_active": lane == ProviderLane.LOCAL,
        "external_providers_enabled": settings.nova_external_providers_enabled,
        "providers": [
            {"kind": p.kind, "configured": p.configured, "enabled": p.enabled}
            for p in external_provider_status(settings)
        ],
    }
