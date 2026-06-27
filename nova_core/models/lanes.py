"""NOVA model lane definitions and recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nova_core.schemas.settings import Settings

LANE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "local_fast": {
        "description": "Fast local chat/clarification",
        "candidates": ("qwen2.5:7b", "llama3.2"),
        "env": "NOVA_LOCAL_MODEL",
    },
    "local_coder": {
        "description": "Code-focused local model",
        "candidates": ("qwen2.5-coder:7b", "qwen3-coder", "deepseek-coder-v2"),
        "env": "NOVA_CODER_MODEL",
    },
    "local_reasoning": {
        "description": "Long-context reasoning",
        "candidates": ("glm-4.5-air", "glm-4.5", "glm-5.2"),
        "env": "NOVA_REASONING_MODEL",
    },
    "external_coding": {
        "description": "External Forge engines",
        "candidates": ("openhands", "claude_code_cli", "codex_cli", "cursor_cli"),
        "env": "NOVA_FORGE_DEFAULT_ENGINE",
    },
    "anthropic_reasoning": {
        "description": "Anthropic Claude API for clarification and review",
        "candidates": ("claude-3-5-sonnet-latest",),
        "env": "NOVA_ANTHROPIC_MODEL",
    },
}


@dataclass(frozen=True)
class LaneStatus:
    lane: str
    configured: str
    installed: bool
    recommended: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "lane": self.lane,
            "configured": self.configured,
            "installed": self.installed,
            "recommended": self.recommended,
        }


def _installed_tags(settings: Settings) -> list[str]:
    import httpx

    url = f"{settings.nova_ollama_base_url.rstrip('/')}/api/tags"
    try:
        resp = httpx.get(url, timeout=3.0)
        resp.raise_for_status()
        return [str(m.get("name", "")) for m in resp.json().get("models", []) if m.get("name")]
    except Exception:
        return []


def _is_installed(model: str, installed: list[str]) -> bool:
    if not model or model == "(auto)":
        return True
    if model in installed:
        return True
    prefix = model.split(":")[0]
    return any(name.startswith(prefix) for name in installed)


def lane_statuses(settings: Settings | None = None) -> list[LaneStatus]:
    settings = settings or Settings()
    installed_tags = _installed_tags(settings)
    mapping = {
        "local_fast": settings.nova_local_model or settings.nova_qwen_model or "(auto)",
        "local_coder": settings.nova_coder_model or "(not set)",
        "local_reasoning": getattr(settings, "nova_reasoning_model", "") or "(not set)",
        "external_coding": (
            getattr(settings, "nova_forge_default_engine", "") or "deterministic_template"
        ),
        "anthropic_reasoning": getattr(settings, "nova_anthropic_model", "") or "(not set)",
    }
    from nova_core.providers.reasoning_lane import anthropic_configured

    rows: list[LaneStatus] = []
    for lane, meta in LANE_DEFINITIONS.items():
        configured = mapping.get(lane, "(not set)")
        recommended = str(meta["candidates"][0])
        if lane == "anthropic_reasoning":
            lane_ready = anthropic_configured(settings)
        elif lane == "external_coding":
            lane_ready = configured != "(not set)"
        else:
            lane_ready = _is_installed(configured, installed_tags)
        rows.append(
            LaneStatus(
                lane=lane,
                configured=configured,
                installed=lane_ready,
                recommended=recommended,
            )
        )
    return rows


def recommend_lanes(settings: Settings | None = None) -> dict[str, str]:
    settings = settings or Settings()
    installed = _installed_tags(settings)
    rec: dict[str, str] = {}
    for lane, meta in LANE_DEFINITIONS.items():
        if lane == "anthropic_reasoning":
            from nova_core.providers.reasoning_lane import anthropic_configured

            rec[lane] = (
                settings.nova_anthropic_model or str(meta["candidates"][0])
                if anthropic_configured(settings)
                else "local fallback"
            )
            continue
        for candidate in meta["candidates"]:
            if lane == "external_coding":
                rec[lane] = str(candidate)
                break
            if _is_installed(str(candidate), installed):
                rec[lane] = str(candidate)
                break
        else:
            rec[lane] = str(meta["candidates"][0])
    return rec
