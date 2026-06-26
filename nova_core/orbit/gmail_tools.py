"""Gmail API helpers — drafts and send via OAuth access tokens."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

import httpx

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _encode_message(to: str, subject: str, body: str) -> str:
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    return raw.rstrip("=")


def create_gmail_draft(
    access_token: str,
    *,
    to: str,
    subject: str,
    body: str,
    timeout: float = 15.0,
) -> str:
    raw = _encode_message(to, subject, body)
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {"message": {"raw": raw}}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{GMAIL_API_BASE}/drafts",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    draft_id = str(data.get("id", ""))
    if not draft_id:
        raise RuntimeError("Gmail draft response missing id")
    return draft_id


def send_gmail_draft(
    access_token: str,
    *,
    draft_id: str,
    timeout: float = 15.0,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{GMAIL_API_BASE}/drafts/{draft_id}/send",
            headers=headers,
            json={},
        )
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, dict) else {"raw": data}


def send_gmail_message(
    access_token: str,
    *,
    to: str,
    subject: str,
    body: str,
    timeout: float = 15.0,
) -> dict[str, Any]:
    raw = _encode_message(to, subject, body)
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {"raw": raw}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{GMAIL_API_BASE}/messages/send",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, dict) else {"raw": data}


def fetch_profile_email(access_token: str, *, timeout: float = 10.0) -> str | None:
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=timeout) as client:
        response = client.get(f"{GMAIL_API_BASE}/profile", headers=headers)
        response.raise_for_status()
        data = response.json()
    email = data.get("emailAddress")
    return str(email) if email else None


def redact_token_location(service: str, account: str) -> str:
    return f"keychain://{service}/{account} (redacted)"
