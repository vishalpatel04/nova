"""Provider routing foundation — no paid calls without explicit configuration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ProviderName(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    QWEN = "qwen"
    DEEPSEEK = "deepseek"
    LOCAL = "local"


@dataclass(frozen=True)
class ProviderConfig:
    default_provider: ProviderName = ProviderName.LOCAL
    model_name: str = "llama3.2"
    local_endpoint_url: str = "http://localhost:11434"
    prefer_free_local: bool = True
    openai_configured: bool = False
    anthropic_configured: bool = False
    qwen_configured: bool = False
    deepseek_configured: bool = False
    local_configured: bool = False


@dataclass(frozen=True)
class RoutingDecision:
    provider: ProviderName
    model_name: str
    mode: str
    paid_call_allowed: bool
    reason: str


class ProviderRouter:
    """Routes chat intents to rule-based, local/free, or stronger configured models."""

    SIMPLE_INTENTS = frozenset(
        {
            "system_status",
            "devices",
            "worker_status",
            "recent_missions",
            "capabilities",
            "help",
            "list_directory",
            "read_file",
            "ripgrep_search",
            "create_system_status_mission",
        }
    )
    PLANNING_KEYWORDS = ("architecture", "design", "plan", "refactor", "strategy")

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def route(self, message: str, intent: str | None = None) -> RoutingDecision:
        if intent in self.SIMPLE_INTENTS:
            return RoutingDecision(
                provider=ProviderName.LOCAL,
                model_name=self.config.model_name,
                mode="rule_based",
                paid_call_allowed=False,
                reason="simple_command",
            )

        lowered = message.lower()
        if any(keyword in lowered for keyword in self.PLANNING_KEYWORDS):
            return self._strongest_available(reason="planning_task")

        if self.config.prefer_free_local and self.config.local_configured:
            return RoutingDecision(
                provider=ProviderName.LOCAL,
                model_name=self.config.model_name,
                mode="local_stub",
                paid_call_allowed=False,
                reason="prefer_free_local",
            )

        return RoutingDecision(
            provider=self.config.default_provider,
            model_name=self.config.model_name,
            mode="degraded_rule_based",
            paid_call_allowed=False,
            reason="no_paid_provider_configured",
        )

    def _strongest_available(self, *, reason: str) -> RoutingDecision:
        if self.config.anthropic_configured:
            return RoutingDecision(
                provider=ProviderName.ANTHROPIC,
                model_name=self.config.model_name,
                mode="paid_stub",
                paid_call_allowed=True,
                reason=reason,
            )
        if self.config.openai_configured:
            return RoutingDecision(
                provider=ProviderName.OPENAI,
                model_name=self.config.model_name,
                mode="paid_stub",
                paid_call_allowed=True,
                reason=reason,
            )
        if self.config.local_configured:
            return RoutingDecision(
                provider=ProviderName.LOCAL,
                model_name=self.config.model_name,
                mode="local_stub",
                paid_call_allowed=False,
                reason="degraded_no_paid_key",
            )
        return RoutingDecision(
            provider=ProviderName.LOCAL,
            model_name=self.config.model_name,
            mode="degraded_rule_based",
            paid_call_allowed=False,
            reason="degraded_no_provider",
        )

    async def invoke_stub(self, decision: RoutingDecision, prompt: str) -> dict[str, Any]:
        if decision.paid_call_allowed and decision.mode == "paid_stub":
            return {
                "provider": decision.provider.value,
                "model": decision.model_name,
                "response": (
                    "Provider routing selected a stronger model, but Phase 3A only "
                    "returns stub responses for non-command chat."
                ),
            }
        return {
            "provider": decision.provider.value,
            "model": decision.model_name,
            "response": (
                "I can help with system status, devices, worker status, recent missions, "
                "safe read-only file tools, and help. Try: `system status` or `help`."
            ),
        }
