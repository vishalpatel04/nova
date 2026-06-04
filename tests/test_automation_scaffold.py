"""Automation provider scaffold tests."""

import pytest

from nova_core.automation.base import (
    NOT_IMPLEMENTED_MESSAGE,
    AutomationProviderKind,
    AutomationRegistry,
)


@pytest.mark.asyncio
async def test_automation_execution_not_implemented() -> None:
    registry = AutomationRegistry()
    provider = registry.get(AutomationProviderKind.N8N)
    result = await provider.execute("run_workflow", {"workflow_id": "demo"})
    assert result.success is False
    assert result.error == NOT_IMPLEMENTED_MESSAGE


def test_registry_lists_planned_providers() -> None:
    registry = AutomationRegistry()
    assert set(registry.list_planned()) == {"n8n", "openclaw", "shortcuts"}
