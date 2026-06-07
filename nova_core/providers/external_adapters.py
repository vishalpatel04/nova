"""External provider adapter scaffolds — disabled by default, no paid calls in tests."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from nova_core.providers.trust_lanes import (
    ExternalProviderKind,
    TrustLaneDecision,
    evaluate_external_call,
)
from nova_core.schemas.settings import Settings


@dataclass(frozen=True)
class AdapterResult:
    content: str
    provider: str
    blocked: bool = False
    reason: str | None = None


class ExternalProviderAdapter(ABC):
    kind: ExternalProviderKind

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(
        self,
        *,
        file_paths: list[str] | None = None,
        cloud_send_approved: bool = False,
    ) -> TrustLaneDecision:
        return evaluate_external_call(
            self.settings,
            provider=self.kind,
            file_paths=file_paths,
            cloud_send_approved=cloud_send_approved,
        )

    @abstractmethod
    async def infer(self, prompt: str, *, intent: str = "external") -> AdapterResult: ...


class AnthropicAdapter(ExternalProviderAdapter):
    kind = ExternalProviderKind.ANTHROPIC

    async def infer(self, prompt: str, *, intent: str = "external") -> AdapterResult:
        decision = self.evaluate()
        if not decision.allowed:
            return AdapterResult(
                content="",
                provider=self.kind.value,
                blocked=True,
                reason=decision.reason,
            )
        _ = prompt, intent
        return AdapterResult(
            content="",
            provider=self.kind.value,
            blocked=True,
            reason="Anthropic adapter scaffold — not invoked in Milestone 3",
        )


class OpenAIAdapter(ExternalProviderAdapter):
    kind = ExternalProviderKind.OPENAI

    async def infer(self, prompt: str, *, intent: str = "external") -> AdapterResult:
        decision = self.evaluate()
        if not decision.allowed:
            return AdapterResult(
                content="",
                provider=self.kind.value,
                blocked=True,
                reason=decision.reason,
            )
        _ = prompt, intent
        return AdapterResult(
            content="",
            provider=self.kind.value,
            blocked=True,
            reason="OpenAI adapter scaffold — not invoked in Milestone 3",
        )


class CodexCliAdapter(ExternalProviderAdapter):
    kind = ExternalProviderKind.CODEX_CLI

    async def infer(self, prompt: str, *, intent: str = "external") -> AdapterResult:
        decision = self.evaluate()
        if not decision.allowed:
            return AdapterResult(
                content="",
                provider=self.kind.value,
                blocked=True,
                reason=decision.reason,
            )
        _ = prompt, intent
        return AdapterResult(
            content="",
            provider=self.kind.value,
            blocked=True,
            reason="Codex CLI adapter scaffold — not invoked in Milestone 3",
        )
