"""openWakeWord adapter — optional local wake-word detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WakeWordStatus:
    available: bool
    backend: str
    setup_hint: str
    model: str | None = None


def openwakeword_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("openwakeword") is not None


def status() -> WakeWordStatus:
    if openwakeword_available():
        return WakeWordStatus(
            available=True,
            backend="openwakeword",
            setup_hint="openWakeWord installed. Run: nova voice setup-openwakeword",
            model="hey_jarvis_v0.1",
        )
    return WakeWordStatus(
        available=False,
        backend="transcript_phrase",
        setup_hint=(
            "openWakeWord not installed.\n"
            "  pip install openwakeword\n"
            "  nova voice setup-openwakeword\n"
            "Fallback: transcript phrase detection (hey nova / okay nova / nova)."
        ),
    )


def setup_hint_markdown() -> str:
    return status().setup_hint


def detect_wake_in_audio(_audio_bytes: bytes) -> dict[str, Any]:
    """Placeholder for live mic detection — requires openWakeWord + audio stream."""
    if not openwakeword_available():
        return {"detected": False, "reason": "openwakeword_unavailable"}
    return {"detected": False, "reason": "use_transcript_simulation_in_ci"}
