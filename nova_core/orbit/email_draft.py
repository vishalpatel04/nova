"""Gmail/local email draft artifacts for Orbit."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nova_core.agent_os.workspace import workspace_root


def _drafts_dir() -> Path:
    path = workspace_root() / ".nova-email-drafts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class EmailDraft:
    draft_id: str
    to: str
    subject: str
    body: str
    source: str
    status: str
    evidence_path: str
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    gmail_draft_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "to": self.to,
            "subject": self.subject,
            "body": self.body,
            "source": self.source,
            "status": self.status,
            "evidence_path": self.evidence_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "gmail_draft_id": self.gmail_draft_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmailDraft:
        return cls(
            draft_id=str(data["draft_id"]),
            to=str(data.get("to", "")),
            subject=str(data.get("subject", "")),
            body=str(data.get("body", "")),
            source=str(data.get("source", "local")),
            status=str(data.get("status", "awaiting_send_approval")),
            evidence_path=str(data.get("evidence_path", "")),
            created_at=str(data.get("created_at", _utc_now())),
            updated_at=str(data.get("updated_at", _utc_now())),
            gmail_draft_id=data.get("gmail_draft_id"),
            metadata=dict(data.get("metadata") or {}),
        )


class EmailDraftStore:
    def save(self, draft: EmailDraft) -> None:
        path = _drafts_dir() / f"{draft.draft_id}.json"
        draft.evidence_path = str(path)
        draft.updated_at = _utc_now()
        path.write_text(json.dumps(draft.to_dict(), indent=2), encoding="utf-8")

    def load(self, draft_id: str) -> EmailDraft | None:
        path = _drafts_dir() / f"{draft_id}.json"
        if not path.exists():
            return None
        return EmailDraft.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in _drafts_dir().glob("*.json"))

    def latest_awaiting_send(self) -> EmailDraft | None:
        candidates: list[EmailDraft] = []
        for draft_id in self.list_ids():
            draft = self.load(draft_id)
            if draft is not None and draft.status == "awaiting_send_approval":
                candidates.append(draft)
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.updated_at)


def resolve_recipient_hint(recipient: str | None) -> str:
    if not recipient:
        return "investor@example.com"
    cleaned = recipient.strip()
    if "@" in cleaned:
        return cleaned
    slug = re.sub(r"[^a-z0-9]+", "", cleaned.lower()) or "contact"
    return f"{slug}@example.com"


def build_investor_update_email(
    *,
    topic: str,
    recipient: str | None,
    preview_url: str | None = None,
    app_name: str | None = None,
) -> tuple[str, str, str]:
    to = resolve_recipient_hint(recipient)
    name = app_name or topic
    subject = f"Investor update: {name}"
    preview_line = (
        f"\nLive preview: {preview_url}\n"
        if preview_url
        else "\n(Local preview available in NOVA workspace.)\n"
    )
    body = (
        f"Hi,\n\n"
        f"I wanted to share a quick update on {name}.\n\n"
        f"NOVA Agent OS generated and validated the app locally, including build checks"
        f" and preview verification.{preview_line}\n"
        f"Happy to walk through the demo live.\n\n"
        f"Best,\n"
        f"NOVA"
    )
    return to, subject, body


def try_create_gmail_draft(
    *,
    to: str,
    subject: str,
    body: str,
    gmail_enabled: bool,
) -> tuple[str, str | None]:
    if not gmail_enabled:
        return "local", None
    try:
        from apps.api.services.gmail_draft_service import GmailDraftService
        from nova_core.schemas.settings import Settings

        service = GmailDraftService(Settings())
        if not service.is_configured():
            return "local", None
        source, draft_id = service.create_draft(to=to, subject=subject, body=body)
        return source, draft_id
    except Exception:
        return "local", None
