"""Phase 3B provider runtime with local-first fallback and telemetry."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from nova_core.providers.router import ProviderName
from nova_core.schemas.settings import Settings


@dataclass(frozen=True)
class ProviderHealth:
    provider: ProviderName
    configured: bool
    paid: bool
    healthy: bool
    mode: str
    detail: str | None = None


@dataclass(frozen=True)
class InferenceRequest:
    prompt: str
    system_prompt: str = "You are NOVA, a concise desktop AI assistant."
    intent: str = "general"
    stream: bool = False


@dataclass(frozen=True)
class InferenceResult:
    provider: ProviderName
    model: str
    content: str
    mode: str
    input_tokens: int
    output_tokens: int
    fallback_used: bool = False
    error: str | None = None


class ProviderRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timeout = httpx.Timeout(settings.nova_provider_timeout_seconds)

    @property
    def paid_enabled(self) -> bool:
        return self.settings.nova_paid_providers_enabled

    def configured_chain(self) -> list[ProviderName]:
        chain = [
            ProviderName.LOCAL,
            ProviderName.QWEN,
            ProviderName.DEEPSEEK,
        ]
        if self.paid_enabled:
            chain.extend([ProviderName.OPENAI, ProviderName.ANTHROPIC])
        return chain

    async def health_checks(self) -> list[ProviderHealth]:
        checks: list[ProviderHealth] = []
        for provider in (
            ProviderName.LOCAL,
            ProviderName.QWEN,
            ProviderName.DEEPSEEK,
            ProviderName.OPENAI,
            ProviderName.ANTHROPIC,
        ):
            checks.append(await self._health(provider))
        return checks

    async def infer(self, request: InferenceRequest) -> InferenceResult:
        last_error: str | None = None
        for index, provider in enumerate(self.configured_chain()):
            if not self._configured(provider):
                continue
            try:
                result = await self._infer_provider(provider, request)
                return InferenceResult(
                    provider=result.provider,
                    model=result.model,
                    content=result.content,
                    mode=result.mode,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    fallback_used=index > 0,
                    error=result.error,
                )
            except Exception as exc:
                last_error = str(exc)
                continue
        return self._local_degraded_response(request, last_error)

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        result = await self.infer(request)
        words = result.content.split(" ")
        for index, word in enumerate(words):
            yield word if index == 0 else f" {word}"
            await asyncio.sleep(0)

    async def _health(self, provider: ProviderName) -> ProviderHealth:
        configured = self._configured(provider)
        paid = provider in {ProviderName.OPENAI, ProviderName.ANTHROPIC}
        if paid and not self.paid_enabled:
            return ProviderHealth(
                provider=provider,
                configured=False,
                paid=True,
                healthy=False,
                mode="disabled",
                detail="paid providers disabled",
            )
        if not configured:
            return ProviderHealth(
                provider=provider,
                configured=False,
                paid=paid,
                healthy=False,
                mode="unconfigured",
            )
        if provider in {ProviderName.LOCAL, ProviderName.QWEN, ProviderName.DEEPSEEK}:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(f"{self._base_url(provider)}/api/tags")
                return ProviderHealth(
                    provider=provider,
                    configured=True,
                    paid=False,
                    healthy=resp.status_code < 500,
                    mode="ollama",
                    detail=str(resp.status_code),
                )
            except Exception as exc:
                return ProviderHealth(
                    provider=provider,
                    configured=True,
                    paid=False,
                    healthy=False,
                    mode="ollama",
                    detail=str(exc),
                )
        return ProviderHealth(
            provider=provider,
            configured=configured,
            paid=paid,
            healthy=True,
            mode="configured",
        )

    def _configured(self, provider: ProviderName) -> bool:
        if provider == ProviderName.LOCAL:
            return bool(self.settings.nova_ollama_base_url)
        if provider == ProviderName.QWEN:
            return bool(self.settings.nova_qwen_base_url)
        if provider == ProviderName.DEEPSEEK:
            return bool(self.settings.nova_deepseek_base_url)
        if provider == ProviderName.OPENAI:
            return self.paid_enabled and bool(self.settings.nova_openai_api_key)
        if provider == ProviderName.ANTHROPIC:
            return self.paid_enabled and bool(self.settings.nova_anthropic_api_key)
        return False

    def _base_url(self, provider: ProviderName) -> str:
        if provider == ProviderName.QWEN:
            return self.settings.nova_qwen_base_url.rstrip("/")
        if provider == ProviderName.DEEPSEEK:
            return self.settings.nova_deepseek_base_url.rstrip("/")
        return self.settings.nova_ollama_base_url.rstrip("/")

    async def _infer_provider(
        self, provider: ProviderName, request: InferenceRequest
    ) -> InferenceResult:
        if provider in {ProviderName.LOCAL, ProviderName.QWEN, ProviderName.DEEPSEEK}:
            return await self._infer_ollama(provider, request)
        if provider == ProviderName.OPENAI:
            return await self._infer_openai(request)
        if provider == ProviderName.ANTHROPIC:
            return await self._infer_anthropic(request)
        raise RuntimeError(f"Unsupported provider: {provider}")

    async def _infer_ollama(
        self, provider: ProviderName, request: InferenceRequest
    ) -> InferenceResult:
        model = {
            ProviderName.QWEN: "qwen2.5",
            ProviderName.DEEPSEEK: "deepseek-r1",
        }.get(provider, "llama3.2")
        payload = {
            "model": model,
            "prompt": f"{request.system_prompt}\n\nUser: {request.prompt}\nNOVA:",
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self._base_url(provider)}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
        content = str(data.get("response", "")).strip()
        return InferenceResult(
            provider=provider,
            model=model,
            content=content or self._default_help(),
            mode="local_ollama",
            input_tokens=self._estimate_tokens(request.prompt),
            output_tokens=self._estimate_tokens(content),
        )

    async def _infer_openai(self, request: InferenceRequest) -> InferenceResult:
        headers = {"Authorization": f"Bearer {self.settings.nova_openai_api_key}"}
        model = "gpt-4.1-mini"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        content = str(data["choices"][0]["message"]["content"]).strip()
        usage = data.get("usage", {})
        return InferenceResult(
            provider=ProviderName.OPENAI,
            model=model,
            content=content,
            mode="paid_openai",
            input_tokens=int(usage.get("prompt_tokens", self._estimate_tokens(request.prompt))),
            output_tokens=int(usage.get("completion_tokens", self._estimate_tokens(content))),
        )

    async def _infer_anthropic(self, request: InferenceRequest) -> InferenceResult:
        headers = {
            "x-api-key": self.settings.nova_anthropic_api_key,
            "anthropic-version": "2023-06-01",
        }
        model = "claude-3-5-haiku-latest"
        payload = {
            "model": model,
            "max_tokens": 800,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        blocks = data.get("content", [])
        content = "\n".join(str(block.get("text", "")) for block in blocks).strip()
        usage = data.get("usage", {})
        return InferenceResult(
            provider=ProviderName.ANTHROPIC,
            model=model,
            content=content,
            mode="paid_anthropic",
            input_tokens=int(usage.get("input_tokens", self._estimate_tokens(request.prompt))),
            output_tokens=int(usage.get("output_tokens", self._estimate_tokens(content))),
        )

    def _local_degraded_response(
        self, request: InferenceRequest, last_error: str | None
    ) -> InferenceResult:
        return InferenceResult(
            provider=ProviderName.LOCAL,
            model="rule_based",
            content=self._default_help(),
            mode="degraded_rule_based",
            input_tokens=self._estimate_tokens(request.prompt),
            output_tokens=40,
            fallback_used=True,
            error=last_error,
        )

    def _default_help(self) -> str:
        return (
            "I can help with system status, devices, sessions, safe read-only files, "
            "repo analysis, approved automation requests, and local-first planning."
        )

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text.split()))


def token_usage_dict(result: InferenceResult) -> dict[str, Any]:
    return {
        "provider": result.provider.value,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "mode": result.mode,
        "fallback_used": result.fallback_used,
        "error": result.error,
    }
