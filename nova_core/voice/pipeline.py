"""Voice command pipeline — transcript to NOVA chat API."""

from __future__ import annotations

import os
from typing import Any

import httpx

from nova_core.voice.wake_word import WakeParseResult, parse_wake_command


def normalize_voice_transcript(transcript: str) -> WakeParseResult:
    return parse_wake_command(transcript)


async def submit_voice_command(
    message: str,
    *,
    api_base: str | None = None,
    token: str | None = None,
    session_id: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    base = (api_base or os.environ.get("NOVA_API_BASE", "http://127.0.0.1:8000")).rstrip("/")
    auth = token or os.environ.get("NOVA_API_TOKEN", "")
    headers = {"Authorization": f"Bearer {auth}"} if auth else {}
    payload: dict[str, Any] = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{base}/api/v1/chat", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, dict) else {"response": str(data)}


def route_voice_transcript(transcript: str) -> tuple[str, str]:
    parsed = normalize_voice_transcript(transcript)
    if not parsed.command.strip():
        return "", ""
    return parsed.command, parsed.wake_phrase or ""
