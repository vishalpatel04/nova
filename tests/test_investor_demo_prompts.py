"""Investor demo prompt routing tests."""

from __future__ import annotations

from nova_core.forge.investor_demo import (
    demo_chat_response,
    is_investor_demo_request,
    parse_investor_demo_request,
)
from nova_core.orchestration.app_request import parse_app_request


def test_parse_calculator_investor_prompt() -> None:
    parsed = parse_app_request("make a calculator app")
    assert parsed is not None
    assert parsed.app_type == "calculator"
    assert is_investor_demo_request("make a calculator app")


def test_parse_kohli_stats_prompt() -> None:
    parsed = parse_investor_demo_request("make a page on Virat Kohli test stats")
    assert parsed is not None
    assert parsed.app_type == "kohli_stats"
    assert parsed.app_name == "Virat Kohli Test Stats"


def test_demo_chat_response_calculator() -> None:
    class _Mission:
        final_report = {
            "demo_chat_summary": (
                "Calculator app generated. Preview is ready. Deploy this app? yes/no"
            )
        }
        artifacts = {}

    text = demo_chat_response(_Mission())  # type: ignore[arg-type]
    assert text == "Calculator app generated. Preview is ready. Deploy this app? yes/no"
