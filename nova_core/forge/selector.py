"""Forge engine selection heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_COMPLEXITY_KEYWORDS = (
    "login",
    "auth",
    "database",
    "postgres",
    "backend",
    "api server",
    "oauth",
    "payment",
    "stripe",
)

_EXPLICIT_ENGINE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\buse openhands\b"), "openhands"),
    (re.compile(r"(?i)\buse claude code\b"), "claude_code_cli"),
    (re.compile(r"(?i)\buse codex\b"), "codex_cli"),
    (re.compile(r"(?i)\bimprove this app\b"), "openhands"),
)


@dataclass(frozen=True)
class EngineSuggestion:
    engine_id: str
    reason: str
    complexity: str = "simple"
    alternatives: tuple[str, ...] = ()
    suggest_external: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "reason": self.reason,
            "complexity": self.complexity,
            "alternatives": list(self.alternatives),
            "suggest_external": self.suggest_external,
        }


def _complexity(request: str) -> str:
    lowered = request.lower()
    if any(keyword in lowered for keyword in _COMPLEXITY_KEYWORDS):
        return "complex"
    if "landing page" in lowered or "todo" in lowered or "calculator" in lowered:
        return "simple"
    return "moderate"


def format_external_engine_message(request: str, settings: Any | None = None) -> str | None:
    """User-facing prompt when a complex build should use an external Forge engine."""
    suggestion = suggest_forge_engine(request)
    if not suggestion.suggest_external:
        return None
    from nova_core.forge.engines.registry import list_engines
    from nova_core.schemas.settings import Settings

    cfg = settings if isinstance(settings, Settings) else Settings()
    engines = list_engines(cfg)
    alt_ids = set(suggestion.alternatives)
    available: list[str] = []
    unavailable: list[str] = []
    for engine in engines:
        if engine.engine_id not in alt_ids:
            continue
        if engine.available():
            available.append(engine.display_name)
        else:
            unavailable.append(engine.display_name)
    lines = [
        suggestion.reason,
        "",
        f"Available Forge engines: {', '.join(available) if available else 'none configured'}",
    ]
    if unavailable:
        lines.append(f"Not configured: {', '.join(unavailable)}")
    lines.extend(
        [
            "",
            "Reply with: use OpenHands | use Claude Code | use Codex | fallback scaffold",
        ]
    )
    return "\n".join(lines)


def suggest_forge_engine(request: str) -> EngineSuggestion:
    for pattern, engine_id in _EXPLICIT_ENGINE_PATTERNS:
        if pattern.search(request):
            return EngineSuggestion(
                engine_id=engine_id,
                reason=f"User requested {engine_id}",
                complexity=_complexity(request),
                alternatives=("deterministic_template",),
            )
    complexity = _complexity(request)
    if complexity == "complex":
        return EngineSuggestion(
            engine_id="deterministic_template",
            reason=(
                "Complex backend/auth/database request detected. "
                "External Forge engines (OpenHands, Claude Code, Codex) recommended if configured."
            ),
            complexity=complexity,
            alternatives=("openhands", "claude_code_cli", "codex_cli"),
            suggest_external=True,
        )
    if complexity == "simple":
        return EngineSuggestion(
            engine_id="deterministic_template",
            reason="Known app pattern — deterministic template engine",
            complexity=complexity,
        )
    return EngineSuggestion(
        engine_id="deterministic_template",
        reason="Moderate request — Qwen clarification + template scaffold",
        complexity=complexity,
        alternatives=("openhands",),
    )
