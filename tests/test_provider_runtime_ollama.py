"""ProviderRuntime Ollama model resolution tests."""

import pytest

from nova_core.providers.runtime import InferenceRequest, ProviderRuntime
from nova_core.schemas.settings import Settings


@pytest.mark.asyncio
async def test_resolve_ollama_model_prefers_installed_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = ProviderRuntime(Settings())

    async def fake_fetch(_provider):  # type: ignore[no-untyped-def]
        return ["qwen2.5:7b"]

    monkeypatch.setattr(runtime, "_fetch_ollama_models", fake_fetch)

    model = await runtime._resolve_ollama_model(
        __import__("nova_core.providers.router", fromlist=["ProviderName"]).ProviderName.LOCAL
    )
    assert model == "qwen2.5:7b"


@pytest.mark.asyncio
async def test_resolve_ollama_model_honors_explicit_setting() -> None:
    runtime = ProviderRuntime(Settings(**{"NOVA_OLLAMA_MODEL": "custom-model:latest"}))
    from nova_core.providers.router import ProviderName

    model = await runtime._resolve_ollama_model(ProviderName.LOCAL)
    assert model == "custom-model:latest"


@pytest.mark.asyncio
async def test_infer_uses_resolved_model_not_hardcoded_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = ProviderRuntime(Settings())
    captured: dict[str, str] = {}

    async def fake_resolve(provider):  # type: ignore[no-untyped-def]
        return "qwen2.5:7b"

    async def fake_infer_ollama(provider, request, *, model: str):  # type: ignore[no-untyped-def]
        captured["model"] = model
        from nova_core.providers.runtime import InferenceResult

        return InferenceResult(
            provider=provider,
            model=model,
            content="Hello from qwen",
            mode="local_ollama",
            input_tokens=1,
            output_tokens=2,
        )

    monkeypatch.setattr(runtime, "_resolve_ollama_model", fake_resolve)
    monkeypatch.setattr(runtime, "_infer_ollama", fake_infer_ollama)
    monkeypatch.setattr(runtime, "_configured", lambda _provider: True)

    result = await runtime.infer(InferenceRequest(prompt="what device is this"))
    assert captured["model"] == "qwen2.5:7b"
    assert result.content == "Hello from qwen"
    assert result.mode == "local_ollama"


@pytest.mark.asyncio
async def test_infer_degraded_when_no_models(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = ProviderRuntime(Settings())

    async def fake_fetch(_provider):  # type: ignore[no-untyped-def]
        return []

    monkeypatch.setattr(runtime, "_fetch_ollama_models", fake_fetch)
    monkeypatch.setattr(runtime, "_configured", lambda _provider: True)

    result = await runtime.infer(InferenceRequest(prompt="hello"))
    assert result.mode == "degraded_rule_based"
    assert "system status" in result.content
