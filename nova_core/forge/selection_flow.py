"""Forge engine selection flow for live NOVAGenie chat."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from nova_core.forge.engines.registry import get_engine, list_engines
from nova_core.forge.selector import _EXPLICIT_ENGINE_PATTERNS, suggest_forge_engine
from nova_core.orchestration.app_request import AppRequest, parse_app_request
from nova_core.schemas.settings import Settings

_REAL_APP_PATTERNS = (
    re.compile(r"(?i)\bmake it real\b"),
    re.compile(r"(?i)\bnot template\b"),
    re.compile(r"(?i)\bproper\b.+\b(login|database|auth)\b"),
)

_ENGINE_REPLY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)^use openhands\b"), "openhands"),
    (re.compile(r"(?i)^use claude code\b"), "claude_code_cli"),
    (re.compile(r"(?i)^use claude\b"), "claude_code_cli"),
    (re.compile(r"(?i)^use codex\b"), "codex_cli"),
    (re.compile(r"(?i)^(use )?fallback\b"), "deterministic_template"),
    (re.compile(r"(?i)^fallback scaffold\b"), "deterministic_template"),
    (re.compile(r"(?i)^deterministic fallback\b"), "deterministic_template"),
    (re.compile(r"(?i)^deterministic is fine\b"), "deterministic_template"),
    (re.compile(r"(?i)^use deterministic\b"), "deterministic_template"),
)

_CANCEL_REPLIES = frozenset({"cancel", "stop", "never mind", "no"})


@dataclass(frozen=True)
class EngineInventoryEntry:
    engine_id: str
    display_name: str
    available: bool
    setup_hint: str
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "display_name": self.display_name,
            "available": self.available,
            "setup_hint": self.setup_hint,
            "capabilities": self.capabilities,
        }


@dataclass(frozen=True)
class ForgeSelectionAnalysis:
    needs_pending: bool
    message: str
    recommended_engine: str
    complexity_reason: str
    direct_engine_id: str | None = None
    direct_engine_available: bool = False
    parsed_app_request: AppRequest | None = None
    available_engines: tuple[EngineInventoryEntry, ...] = ()
    unavailable_engines: tuple[EngineInventoryEntry, ...] = ()
    complexity: str = "simple"

    def to_payload(
        self,
        *,
        raw_request: str,
        workspace_path: str,
        app_spec: dict[str, Any] | None = None,
        ttl_minutes: int = 5,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        return {
            "raw_request": raw_request.strip()[:2000],
            "parsed_app_request": self._serialize_app_request(self.parsed_app_request),
            "recommended_engine": self.recommended_engine,
            "available_engines": [e.to_dict() for e in self.available_engines],
            "unavailable_engines": [e.to_dict() for e in self.unavailable_engines],
            "workspace_path": workspace_path,
            "complexity_reason": self.complexity_reason,
            "complexity": self.complexity,
            "app_spec": app_spec or {},
            "preselected_engine": self.direct_engine_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
        }

    @staticmethod
    def _serialize_app_request(app_request: AppRequest | None) -> dict[str, Any]:
        if app_request is None:
            return {}
        return {
            "app_type": app_request.app_type,
            "app_name": app_request.app_name,
            "runtime": app_request.runtime,
            "raw_user_request": app_request.raw_user_request,
            "features": list(app_request.features),
        }


def _engine_inventory(
    settings: Settings,
) -> tuple[list[EngineInventoryEntry], list[EngineInventoryEntry]]:
    available: list[EngineInventoryEntry] = []
    unavailable: list[EngineInventoryEntry] = []
    for engine in list_engines(settings):
        entry = EngineInventoryEntry(
            engine_id=engine.engine_id,
            display_name=engine.display_name,
            available=engine.available(),
            setup_hint=engine.setup_hint(),
            capabilities=engine.capabilities(),
        )
        if entry.available:
            available.append(entry)
        else:
            unavailable.append(entry)
    return available, unavailable


def _recommend_engine(
    suggestion_engine_id: str,
    available: list[EngineInventoryEntry],
    unavailable: list[EngineInventoryEntry],
) -> str:
    for entry in available:
        if entry.engine_id == suggestion_engine_id:
            return entry.engine_id
    for entry in available:
        if entry.engine_id != "deterministic_template":
            return entry.engine_id
    if unavailable:
        return unavailable[0].engine_id
    return "deterministic_template"


def _format_engine_lines(
    available: list[EngineInventoryEntry],
    unavailable: list[EngineInventoryEntry],
) -> list[str]:
    lines = ["Available Forge engines:"]
    template = next((e for e in available if e.engine_id == "deterministic_template"), None)
    if template:
        lines.append(f"- {template.display_name}: available (template scaffold, limited)")
    for entry in available:
        if entry.engine_id == "deterministic_template":
            continue
        lines.append(f"- {entry.display_name}: available")
    for entry in unavailable:
        if entry.engine_id == "deterministic_template":
            continue
        first_hint = entry.setup_hint.split("\n")[0].strip()
        lines.append(f"- {entry.display_name}: unavailable — {first_hint}")
    return lines


def _setup_hint_block(engine_id: str) -> str:
    if engine_id == "openhands":
        return (
            "OpenHands setup:\n"
            "- Set NOVA_OPENHANDS_URL or NOVA_OPENHANDS_CMD\n"
            "- See docs/OPENHANDS_INTEGRATION.md"
        )
    if engine_id == "claude_code_cli":
        return (
            "Claude Code setup:\n"
            "- Install and login to Claude Code CLI\n"
            "- Ensure `claude` is on PATH, or set NOVA_CLAUDE_CODE_CMD"
        )
    if engine_id == "codex_cli":
        return (
            "Codex setup:\n"
            "- Install and login to Codex CLI\n"
            "- Ensure `codex` is on PATH, or set NOVA_CODEX_CMD"
        )
    return ""


def parse_engine_selection_reply(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    if cleaned.lower() in _CANCEL_REPLIES:
        return "__cancel__"
    for pattern, engine_id in _ENGINE_REPLY_PATTERNS:
        if pattern.search(cleaned):
            return engine_id
    lowered = cleaned.lower()
    if "fallback" in lowered or "deterministic" in lowered:
        return "deterministic_template"
    if "openhands" in lowered:
        return "openhands"
    if "claude" in lowered:
        return "claude_code_cli"
    if "codex" in lowered:
        return "codex_cli"
    return None


def _needs_forge_selection(request: str) -> bool:
    suggestion = suggest_forge_engine(request)
    if suggestion.suggest_external:
        return True
    if any(pattern.search(request) for pattern in _REAL_APP_PATTERNS):
        return True
    return any(pattern.search(request) for pattern, _engine_id in _EXPLICIT_ENGINE_PATTERNS)


def _has_fallback_choice(request: str) -> bool:
    lowered = request.lower()
    return any(
        phrase in lowered
        for phrase in (
            "fallback scaffold",
            "deterministic fallback",
            "use fallback",
            "deterministic is fine",
        )
    )


def analyze_forge_selection(request: str, settings: Settings) -> ForgeSelectionAnalysis | None:
    if _has_fallback_choice(request):
        return None

    if not _needs_forge_selection(request):
        return None

    parsed = parse_app_request(request)
    if parsed is None:
        parsed = parse_app_request(f"build a simple web app for {request}")

    suggestion = suggest_forge_engine(request)
    available, unavailable = _engine_inventory(settings)
    recommended = _recommend_engine(suggestion.engine_id, available, unavailable)

    explicit_engine: str | None = None
    if suggestion.engine_id != "deterministic_template" and not suggestion.suggest_external:
        explicit_engine = suggestion.engine_id

    if explicit_engine:
        engine = get_engine(explicit_engine, settings)
        if engine is not None and engine.available():
            return ForgeSelectionAnalysis(
                needs_pending=False,
                message="",
                recommended_engine=explicit_engine,
                complexity_reason=suggestion.reason,
                direct_engine_id=explicit_engine,
                direct_engine_available=True,
                parsed_app_request=parsed,
                available_engines=tuple(available),
                unavailable_engines=tuple(unavailable),
                complexity=suggestion.complexity,
            )
        hint = engine.setup_hint() if engine is not None else "Engine not found."
        setup = _setup_hint_block(explicit_engine)
        lines = [
            f"{engine.display_name if engine else explicit_engine} is not configured yet.",
            "",
            setup or hint,
            "",
            *_format_engine_lines(available, unavailable),
            "",
            "Choose: use fallback | cancel",
        ]
        return ForgeSelectionAnalysis(
            needs_pending=True,
            message="\n".join(lines),
            recommended_engine=explicit_engine,
            complexity_reason=suggestion.reason,
            direct_engine_id=explicit_engine,
            direct_engine_available=False,
            parsed_app_request=parsed,
            available_engines=tuple(available),
            unavailable_engines=tuple(unavailable),
            complexity=suggestion.complexity,
        )

    rec_label = (
        recommended.replace("_", " ").title()
        if recommended != "deterministic_template"
        else "deterministic template (limited)"
    )
    lines = [
        (
            "This is more than a template app. "
            "I can build a real scaffold with auth/database using Forge."
        ),
        "",
        *_format_engine_lines(available, unavailable),
        "",
        f"Recommended: {rec_label}.",
        "",
        (
            "Should I use OpenHands, use Claude Code, use Codex, "
            "use deterministic fallback, or cancel?"
        ),
    ]
    return ForgeSelectionAnalysis(
        needs_pending=True,
        message="\n".join(lines),
        recommended_engine=recommended,
        complexity_reason=suggestion.reason,
        parsed_app_request=parsed,
        available_engines=tuple(available),
        unavailable_engines=tuple(unavailable),
        complexity=suggestion.complexity,
    )


def build_unavailable_engine_message(engine_id: str, settings: Settings) -> str:
    engine = get_engine(engine_id, settings)
    if engine is None:
        return f"Unknown engine: {engine_id}"
    if engine.available():
        return f"{engine.display_name} is available."
    setup = _setup_hint_block(engine_id) or engine.setup_hint()
    return (
        f"{engine.display_name} is not configured yet.\n\n"
        f"{setup}\n\n"
        "Choose: use deterministic fallback | cancel"
    )
