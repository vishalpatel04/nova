"""Provider routing foundation tests."""

import pytest

from nova_core.providers.router import ProviderConfig, ProviderName, ProviderRouter


def test_simple_intent_uses_rule_based_free_route() -> None:
    router = ProviderRouter(ProviderConfig())
    decision = router.route("system status", intent="system_status")
    assert decision.mode == "rule_based"
    assert decision.paid_call_allowed is False


def test_prefer_free_local_default() -> None:
    router = ProviderRouter(
        ProviderConfig(prefer_free_local=True, local_configured=True, openai_configured=True)
    )
    decision = router.route("what time is it?", intent="general")
    assert decision.provider == ProviderName.LOCAL
    assert decision.paid_call_allowed is False


@pytest.mark.asyncio
async def test_no_paid_call_without_explicit_config() -> None:
    router = ProviderRouter(ProviderConfig(openai_configured=False, anthropic_configured=False))
    decision = router.route("design the architecture", intent="general")
    assert decision.paid_call_allowed is False
    stub = await router.invoke_stub(decision, "design the architecture")
    assert "stub" in decision.mode or "degraded" in decision.mode
    assert stub["provider"] == decision.provider.value
