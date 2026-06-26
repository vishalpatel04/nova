"""Qwen-assisted email composition with deterministic fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from nova_core.orbit.email_draft import build_investor_update_email
from nova_core.providers.runtime import InferenceRequest, ProviderRuntime
from nova_core.schemas.settings import Settings

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


class EmailComposition(BaseModel):
    to: str
    subject: str
    body: str
    attachments: list[str] = Field(default_factory=list)
    tone: str = "professional"
    notes: str = ""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            pass
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def deterministic_email(
    *,
    topic: str,
    recipient: str | None,
    preview_url: str | None,
    app_name: str | None,
    purpose: str,
) -> EmailComposition:
    to, subject, body = build_investor_update_email(
        topic=topic,
        recipient=recipient,
        preview_url=preview_url,
        app_name=app_name,
    )
    attachments: list[str] = []
    if preview_url:
        attachments.append(preview_url)
    if purpose == "follow_up":
        subject = f"Follow-up: {app_name or topic}"
        body = body.replace("quick update", "brief follow-up")
    return EmailComposition(to=to, subject=subject, body=body, attachments=attachments)


async def compose_email(
    settings: Settings,
    *,
    purpose: str,
    recipient: str | None,
    topic: str,
    preview_url: str | None,
    app_name: str | None,
    mission_summary: str | None = None,
    tone: str = "professional",
    edit_instruction: str | None = None,
    existing: EmailComposition | None = None,
) -> EmailComposition:
    fallback = deterministic_email(
        topic=topic,
        recipient=recipient,
        preview_url=preview_url,
        app_name=app_name,
        purpose=purpose,
    )
    runtime = ProviderRuntime(settings)
    context_lines = [
        f"Purpose: {purpose}",
        f"Topic: {topic}",
        f"Recipient: {recipient or 'unknown'}",
        f"App name: {app_name or 'n/a'}",
        f"Preview URL: {preview_url or 'n/a'}",
        f"Mission summary: {mission_summary or 'n/a'}",
        f"Tone: {tone}",
    ]
    if existing:
        context_lines.extend(
            [
                f"Current subject: {existing.subject}",
                f"Current body:\n{existing.body}",
            ]
        )
    if edit_instruction:
        context_lines.append(f"Edit instruction: {edit_instruction}")
    prompt = (
        "Draft an email for NOVA Orbit. Return ONLY JSON:\n"
        '{"to":"email","subject":"string","body":"string","attachments":["url"],'
        '"tone":"string","notes":"string"}\n'
        "Keep body concise and professional. Include preview URL in body when provided.\n"
        "Never invent a recipient email — use the provided recipient or "
        f"{fallback.to!r}.\n\n" + "\n".join(context_lines)
    )
    try:
        result = await runtime.infer(
            InferenceRequest(
                prompt=prompt,
                system_prompt="You output strict JSON email drafts for NOVA Orbit.",
                intent="orbit_email_compose",
            )
        )
        if result.error or not result.content.strip():
            return fallback
        payload = _extract_json_object(result.content)
        if payload is None:
            return fallback
        composition = EmailComposition.model_validate(payload)
        if not composition.to:
            composition.to = fallback.to
        if preview_url and preview_url not in composition.body:
            composition.attachments = list({*composition.attachments, preview_url})
        return composition
    except Exception:
        return fallback
