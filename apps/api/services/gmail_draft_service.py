"""Gmail draft/send service used by Orbit after OAuth."""

from __future__ import annotations

from typing import Any

from apps.api.services.gmail_oauth_service import GmailOAuthService
from nova_core.orbit.gmail_tools import create_gmail_draft, send_gmail_draft, send_gmail_message
from nova_core.schemas.settings import Settings


class GmailDraftService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.oauth = GmailOAuthService(settings)

    def is_configured(self) -> bool:
        status = self.oauth.status()
        return bool(status.get("configured"))

    def create_draft(self, *, to: str, subject: str, body: str) -> tuple[str, str]:
        token = self.oauth.get_access_token()
        if not token:
            raise RuntimeError("Gmail is not connected. Run: nova gmail auth")
        draft_id = create_gmail_draft(token, to=to, subject=subject, body=body)
        return "gmail", draft_id

    def send_draft(self, *, draft_id: str) -> dict[str, Any]:
        if not self.settings.nova_gmail_send_enabled:
            raise RuntimeError(
                "Gmail send is disabled. Set NOVA_GMAIL_SEND_ENABLED=true after review."
            )
        token = self.oauth.get_access_token()
        if not token:
            raise RuntimeError("Gmail is not connected.")
        return send_gmail_draft(token, draft_id=draft_id)

    def send_message(self, *, to: str, subject: str, body: str) -> dict[str, Any]:
        if not self.settings.nova_gmail_send_enabled:
            raise RuntimeError("Gmail send is disabled.")
        token = self.oauth.get_access_token()
        if not token:
            raise RuntimeError("Gmail is not connected.")
        return send_gmail_message(token, to=to, subject=subject, body=body)
