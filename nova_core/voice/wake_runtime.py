"""Unified wake runtime — openWakeWord when available, phrase fallback."""

from __future__ import annotations

from dataclasses import dataclass

from nova_core.voice.openwakeword_adapter import status as ow_status
from nova_core.voice.wake_word import WakeParseResult, parse_wake_command


@dataclass
class WakeRuntimeStatus:
    openwakeword: bool
    phrase_fallback: bool
    backend: str
    setup_hint: str


def runtime_status() -> WakeRuntimeStatus:
    ow = ow_status()
    return WakeRuntimeStatus(
        openwakeword=ow.available,
        phrase_fallback=True,
        backend=ow.backend,
        setup_hint=ow.setup_hint,
    )


def process_transcript(transcript: str) -> WakeParseResult:
    return parse_wake_command(transcript)
