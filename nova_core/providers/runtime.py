"""Phase 3B provider runtime with local-first fallback and telemetry."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from nova_core.providers.router import ProviderName
from nova_core.providers.stream_context import StreamCancelToken, StreamTelemetry
from nova_core.schemas.settings import Settings
from nova_core.sentry.logging import get_logger
from nova_core.tools.provider_security import scrub_runtime_detail

logger = get_logger("nova.providers.runtime")

_PREFERRED_OLLAMA_MODELS: dict[ProviderName, tuple[str, ...]] = {
    ProviderName.LOCAL: ("llama3.2", "llama3.2:latest"),
    ProviderName.QWEN: ("qwen2.5:7b", "qwen2.5", "qwen2.5:latest"),
    ProviderName.DEEPSEEK: ("deepseek-r1", "deepseek-r1:latest"),
}

_OLLAMA_PREFIX_HINTS: dict[ProviderName, str] = {
    ProviderName.LOCAL: "llama",
    ProviderName.QWEN: "qwen",
    ProviderName.DEEPSEEK: "deepseek",
}


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
    fallback_reason: str | None = None
    error: str | None = None


class ProviderRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timeout = httpx.Timeout(settings.nova_provider_timeout_seconds)
        self._ollama_tags_cache: dict[str, list[str]] = {}

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
        last_reason: str | None = None
        for index, provider in enumerate(self.configured_chain()):
            if not self._configured(provider):
                logger.info(
                    "provider_infer_skip_unconfigured",
                    provider=provider.value,
                )
                continue
            try:
                if provider in {ProviderName.LOCAL, ProviderName.QWEN, ProviderName.DEEPSEEK}:
                    model = await self._resolve_ollama_model(provider)
                    logger.info(
                        "provider_infer_attempt",
                        provider=provider.value,
                        model=model,
                        url=f"{self._base_url(provider)}/api/generate",
                    )
                    result = await self._infer_provider(provider, request, model=model)
                else:
                    logger.info("provider_infer_attempt", provider=provider.value)
                    result = await self._infer_provider(provider, request)
                logger.info(
                    "provider_infer_success",
                    provider=result.provider.value,
                    model=result.model,
                    mode=result.mode,
                    output_chars=len(result.content),
                )
                return InferenceResult(
                    provider=result.provider,
                    model=result.model,
                    content=result.content,
                    mode=result.mode,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    fallback_used=index > 0,
                    fallback_reason=result.fallback_reason,
                    error=result.error,
                )
            except Exception as exc:
                last_error = str(exc)
                last_reason = self._classify_fallback_reason(exc)
                logger.warning(
                    "provider_infer_failed",
                    provider=provider.value,
                    reason=last_reason or "provider_unreachable",
                )
                continue
        logger.warning(
            "provider_infer_degraded",
            reason="chain_exhausted",
            last_reason=last_reason,
        )
        return self._local_degraded_response(request, last_error, last_reason)

    async def stream(
        self,
        request: InferenceRequest,
        *,
        cancel: StreamCancelToken | None = None,
        telemetry: StreamTelemetry | None = None,
    ) -> AsyncIterator[str]:
        telemetry = telemetry or StreamTelemetry(stream_id=cancel.stream_id if cancel else "inline")
        for index, provider in enumerate(self.configured_chain()):
            if cancel and cancel.cancelled:
                telemetry.cancelled = True
                break
            if not self._configured(provider):
                continue
            try:
                if provider in {ProviderName.LOCAL, ProviderName.QWEN, ProviderName.DEEPSEEK}:
                    model = await self._resolve_ollama_model(provider)
                    logger.info(
                        "provider_stream_attempt",
                        provider=provider.value,
                        model=model,
                        url=f"{self._base_url(provider)}/api/generate",
                    )
                    async for chunk in self._stream_provider(
                        provider, request, model=model, cancel=cancel
                    ):
                        if cancel and cancel.cancelled:
                            telemetry.cancelled = True
                            break
                        telemetry.token_count += 1
                        telemetry.provider = provider.value
                        telemetry.model = model
                        yield chunk
                    if telemetry.token_count > 0:
                        telemetry.fallback_used = index > 0
                        telemetry.mode = "local_ollama"
                        logger.info(
                            "provider_stream_success",
                            provider=provider.value,
                            model=model,
                            token_count=telemetry.token_count,
                        )
                        return
                else:
                    async for chunk in self._stream_provider(provider, request, cancel=cancel):
                        if cancel and cancel.cancelled:
                            telemetry.cancelled = True
                            break
                        telemetry.token_count += 1
                        telemetry.provider = provider.value
                        yield chunk
                    if telemetry.token_count > 0:
                        telemetry.fallback_used = index > 0
                        telemetry.mode = (
                            "paid"
                            if provider in {ProviderName.OPENAI, ProviderName.ANTHROPIC}
                            else "local_ollama"
                        )
                        return
            except Exception as exc:
                logger.warning(
                    "provider_stream_failed",
                    provider=provider.value,
                    reason=self._classify_fallback_reason(exc) or "provider_unreachable",
                )
                telemetry.error = str(exc)
                telemetry.fallback_reason = self._classify_fallback_reason(exc)
                continue

        logger.warning("provider_stream_degraded", reason="chain_exhausted")

        result = await self.infer(request)
        telemetry.provider = result.provider.value
        telemetry.model = result.model
        telemetry.mode = result.mode
        telemetry.fallback_used = result.fallback_used
        telemetry.fallback_reason = result.fallback_reason
        telemetry.error = result.error
        words = result.content.split(" ")
        for index, word in enumerate(words):
            if cancel and cancel.cancelled:
                telemetry.cancelled = True
                break
            telemetry.token_count += 1
            yield word if index == 0 else f" {word}"
            await asyncio.sleep(0.005)

    def telemetry_from_stream(self, cancel: StreamCancelToken | None) -> StreamTelemetry:
        return StreamTelemetry(stream_id=cancel.stream_id if cancel else "inline")

    def runtime_summary(self) -> dict[str, Any]:
        local_check = None
        try:
            local_check = self.settings.nova_ollama_base_url.strip()
        except Exception:
            local_check = None
        return {
            "local_available": bool(local_check),
            "wake_word_supported": True,
            "voice_on_device_supported": True,
        }

    async def _stream_provider(
        self,
        provider: ProviderName,
        request: InferenceRequest,
        *,
        model: str | None = None,
        cancel: StreamCancelToken | None = None,
    ) -> AsyncIterator[str]:
        if provider in {ProviderName.LOCAL, ProviderName.QWEN, ProviderName.DEEPSEEK}:
            resolved = model or await self._resolve_ollama_model(provider)
            async for chunk in self._stream_ollama(
                provider, request, model=resolved, cancel=cancel
            ):
                yield chunk
            return
        result = await self._infer_provider(provider, request)
        words = result.content.split(" ")
        for index, word in enumerate(words):
            if cancel and cancel.cancelled:
                break
            yield word if index == 0 else f" {word}"
            await asyncio.sleep(0.005)

    async def _stream_ollama(
        self,
        provider: ProviderName,
        request: InferenceRequest,
        *,
        model: str,
        cancel: StreamCancelToken | None = None,
    ) -> AsyncIterator[str]:
        url = f"{self._base_url(provider)}/api/generate"
        payload = {
            "model": model,
            "prompt": f"{request.system_prompt}\n\nUser: {request.prompt}\nNOVA:",
            "stream": True,
        }
        logger.info(
            "ollama_stream_request",
            provider=provider.value,
            model=model,
            url=url,
        )
        async with (
            httpx.AsyncClient(timeout=self.timeout) as client,
            client.stream("POST", url, json=payload) as resp,
        ):
            logger.info(
                "ollama_stream_response",
                provider=provider.value,
                model=model,
                status=resp.status_code,
            )
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", errors="replace")[:300]
                logger.warning(
                    "ollama_stream_error_body",
                    provider=provider.value,
                    model=model,
                    status=resp.status_code,
                    body=scrub_runtime_detail(body),
                )
                resp.raise_for_status()
            async for line in resp.aiter_lines():
                if cancel and cancel.cancelled:
                    break
                if not line:
                    continue
                data = json.loads(line)
                chunk = str(data.get("response", ""))
                if chunk:
                    yield chunk
                if data.get("done"):
                    break

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
        self, provider: ProviderName, request: InferenceRequest, *, model: str | None = None
    ) -> InferenceResult:
        if provider in {ProviderName.LOCAL, ProviderName.QWEN, ProviderName.DEEPSEEK}:
            resolved = model or await self._resolve_ollama_model(provider)
            return await self._infer_ollama(provider, request, model=resolved)
        if provider == ProviderName.OPENAI:
            return await self._infer_openai(request)
        if provider == ProviderName.ANTHROPIC:
            return await self._infer_anthropic(request)
        raise RuntimeError(f"Unsupported provider: {provider}")

    async def _fetch_ollama_models(self, provider: ProviderName) -> list[str]:
        base_url = self._base_url(provider)
        cached = self._ollama_tags_cache.get(base_url)
        if cached is not None:
            return cached
        tags_url = f"{base_url}/api/tags"
        logger.info("ollama_tags_request", provider=provider.value, url=tags_url)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(tags_url)
            logger.info(
                "ollama_tags_response",
                provider=provider.value,
                status=resp.status_code,
            )
            resp.raise_for_status()
            data = resp.json()
        models = [
            str(entry.get("name", "")).strip()
            for entry in data.get("models", [])
            if entry.get("name")
        ]
        self._ollama_tags_cache[base_url] = models
        logger.info(
            "ollama_tags_models",
            provider=provider.value,
            models=models,
        )
        return models

    async def _resolve_ollama_model(self, provider: ProviderName) -> str:
        explicit = {
            ProviderName.LOCAL: self.settings.nova_ollama_model,
            ProviderName.QWEN: self.settings.nova_qwen_model,
            ProviderName.DEEPSEEK: self.settings.nova_deepseek_model,
        }.get(provider, "")
        if explicit:
            logger.info(
                "ollama_model_explicit",
                provider=provider.value,
                model=explicit,
            )
            return explicit

        available = await self._fetch_ollama_models(provider)
        if not available:
            raise RuntimeError(f"No Ollama models available for {provider.value}")

        for candidate in _PREFERRED_OLLAMA_MODELS.get(provider, ()):
            if candidate in available:
                logger.info(
                    "ollama_model_preferred",
                    provider=provider.value,
                    model=candidate,
                )
                return candidate

        prefix = _OLLAMA_PREFIX_HINTS.get(provider, "")
        if prefix:
            for name in available:
                if name.startswith(prefix):
                    logger.info(
                        "ollama_model_prefix_match",
                        provider=provider.value,
                        model=name,
                        prefix=prefix,
                    )
                    return name

        if provider == ProviderName.LOCAL:
            logger.info(
                "ollama_model_local_fallback",
                provider=provider.value,
                model=available[0],
            )
            return available[0]

        raise RuntimeError(f"No matching Ollama model for {provider.value}; available={available}")

    async def _infer_ollama(
        self, provider: ProviderName, request: InferenceRequest, *, model: str
    ) -> InferenceResult:
        url = f"{self._base_url(provider)}/api/generate"
        payload = {
            "model": model,
            "prompt": f"{request.system_prompt}\n\nUser: {request.prompt}\nNOVA:",
            "stream": False,
        }
        logger.info(
            "ollama_infer_request",
            provider=provider.value,
            model=model,
            url=url,
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload)
            logger.info(
                "ollama_infer_response",
                provider=provider.value,
                model=model,
                status=resp.status_code,
            )
            if resp.status_code >= 400:
                body = resp.text[:300]
                logger.warning(
                    "ollama_infer_error_body",
                    provider=provider.value,
                    model=model,
                    status=resp.status_code,
                    body=scrub_runtime_detail(body),
                )
                resp.raise_for_status()
            data = resp.json()
        content = str(data.get("response", "")).strip()
        if not content:
            error = str(data.get("error", "empty Ollama response"))
            logger.warning(
                "ollama_infer_empty_content",
                provider=provider.value,
                model=model,
                error=error,
            )
            raise RuntimeError(error)
        return InferenceResult(
            provider=provider,
            model=model,
            content=content,
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
        self, request: InferenceRequest, last_error: str | None, fallback_reason: str | None
    ) -> InferenceResult:
        return InferenceResult(
            provider=ProviderName.LOCAL,
            model="rule_based",
            content=self._default_help(),
            mode="degraded_rule_based",
            input_tokens=self._estimate_tokens(request.prompt),
            output_tokens=40,
            fallback_used=True,
            fallback_reason=fallback_reason or "provider_unreachable",
            error=last_error,
        )

    def _default_help(self) -> str:
        return (
            "I can help with status, devices, sessions, search, memory, approvals, "
            "background tasks, and local planning."
        )

    def _classify_fallback_reason(self, exc: Exception) -> str | None:
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.ConnectError):
            return "provider_unreachable"
        if isinstance(exc, json.JSONDecodeError):
            return "malformed_response"
        message = str(exc).lower()
        if "empty ollama response" in message:
            return "empty_response"
        if "no ollama models available" in message or "no matching ollama model" in message:
            return "no_model"
        if "invalid json" in message or "malformed" in message:
            return "malformed_response"
        if "timeout" in message:
            return "timeout"
        if "connection" in message:
            return "provider_unreachable"
        return None

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
        "fallback_reason": result.fallback_reason,
        "error": result.fallback_reason,
    }
