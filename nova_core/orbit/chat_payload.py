"""Structured Orbit email payloads for NOVAGenie."""

from __future__ import annotations

from typing import Any

from nova_core.orbit.email_draft import EmailDraft


def build_orbit_email_chat_payload(draft: EmailDraft) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    if draft.status == "awaiting_send_approval":
        actions.extend(
            [
                {
                    "label": "Yes",
                    "action": "approve_email_send",
                    "draft_id": draft.draft_id,
                },
                {
                    "label": "No",
                    "action": "skip_email_send",
                    "draft_id": draft.draft_id,
                },
            ]
        )
        actions.append(
            {
                "label": "Copy Body",
                "action": "copy_text",
                "text": draft.body,
            }
        )
    if draft.evidence_path:
        actions.append(
            {
                "label": "Evidence",
                "action": "copy_text",
                "text": draft.evidence_path,
            }
        )
    attachments = list(draft.metadata.get("attachments") or [])
    source_label = (
        "Gmail draft" if draft.source == "gmail" else "Local artifact (Gmail not configured)"
    )
    short = f"Email draft ready for {draft.to}. Send this email?"
    if draft.status == "skipped":
        short = "Email send skipped."
    if draft.status == "sent":
        short = "Email sent via Gmail."
    elif draft.status == "send_approved":
        evidence = str(draft.metadata.get("send_evidence", ""))
        short = evidence or "Send approval recorded. Gmail is not connected."
    return {
        "type": "orbit_email_draft",
        "draft_id": draft.draft_id,
        "status": draft.status,
        "result": {
            "to": draft.to,
            "subject": draft.subject,
            "body_preview": draft.body[:1200],
            "attachments": attachments,
            "draft_source": source_label,
            "evidence_log": draft.evidence_path,
            "approval_question": "Send this email?"
            if draft.status == "awaiting_send_approval"
            else "",
        },
        "actions": actions,
        "text": short,
    }
