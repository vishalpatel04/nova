"""Anthropic CLI test and error sanitization."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from nova_core.providers.reasoning_lane import (
    DEFAULT_ANTHROPIC_MODEL,
    anthropic_model_name,
    sanitize_anthropic_error,
)
from nova_core.providers.router import ProviderName
from nova_core.providers.runtime import InferenceRequest, InferenceResult, ProviderRuntime
from nova_core.schemas.settings import Settings


def test_default_anthropic_model() -> None:
    settings = Settings()
    assert anthropic_model_name(settings) == DEFAULT_ANTHROPIC_MODEL
    assert DEFAULT_ANTHROPIC_MODEL == "claude-sonnet-4-6"


def test_sanitize_anthropic_error_redacts_key() -> None:
    key = "sk-ant-api03-secretvalue"
    message = f"401 unauthorized for key {key}"
    assert key not in sanitize_anthropic_error(message, api_key=key)
    assert "***" in sanitize_anthropic_error(message, api_key=key)


@pytest.mark.asyncio
async def test_infer_anthropic_direct_no_fallback() -> None:
    settings = Settings(
        NOVA_ANTHROPIC_ENABLED=True,
        ANTHROPIC_API_KEY="sk-ant-test",
        NOVA_ANTHROPIC_MODEL="claude-sonnet-4-6",
    )
    runtime = ProviderRuntime(settings)
    expected = InferenceResult(
        provider=ProviderName.ANTHROPIC,
        model="claude-sonnet-4-6",
        content="OK",
        mode="paid_anthropic",
        input_tokens=1,
        output_tokens=1,
    )
    with patch.object(runtime, "_infer_anthropic", AsyncMock(return_value=expected)) as mock_infer:
        result = await runtime.infer_anthropic_direct(
            InferenceRequest(prompt="Return OK", intent="anthropic_health_check")
        )
    assert result.provider == ProviderName.ANTHROPIC
    mock_infer.assert_awaited_once()


@pytest.mark.asyncio
async def test_infer_anthropic_direct_raises_without_config() -> None:
    settings = Settings(NOVA_ANTHROPIC_ENABLED=False, ANTHROPIC_API_KEY="")
    runtime = ProviderRuntime(settings)
    with pytest.raises(RuntimeError, match="not configured"):
        await runtime.infer_anthropic_direct(
            InferenceRequest(prompt="Return OK", intent="anthropic_health_check")
        )
