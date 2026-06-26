"""Gmail OAuth token storage and refresh for NOVA Orbit."""

from __future__ import annotations

import json
import secrets
import urllib.parse
import webbrowser
from contextlib import suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import httpx

from nova_core.agent_os.workspace import workspace_root
from nova_core.auth import keychain
from nova_core.orbit.gmail_tools import fetch_profile_email, redact_token_location
from nova_core.schemas.settings import Settings

GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


@dataclass(frozen=True)
class GmailTokenBundle:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    scope: str
    token_type: str
    account_email: str | None = None


class GmailOAuthService:
    KEYCHAIN_SERVICE = "com.nova.gmail"
    KEYCHAIN_ACCOUNT = "default"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def client_configured(self) -> bool:
        return bool(self.settings.nova_gmail_client_id and self.settings.nova_gmail_client_secret)

    def _fallback_token_path(self) -> Path:
        return workspace_root() / ".nova-gmail" / "oauth_tokens.json"

    def _load_stored_tokens(self) -> dict[str, Any] | None:
        raw = keychain.read_generic_password(self.KEYCHAIN_SERVICE, self.KEYCHAIN_ACCOUNT)
        if raw:
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        path = self._fallback_token_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _save_tokens(self, bundle: dict[str, Any]) -> None:
        serialized = json.dumps(bundle)
        if keychain.write_generic_password(
            self.KEYCHAIN_SERVICE,
            self.KEYCHAIN_ACCOUNT,
            serialized,
        ):
            return
        path = self._fallback_token_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")
        with suppress(OSError):
            path.chmod(0o600)

    def disconnect(self) -> bool:
        keychain.delete_generic_password(self.KEYCHAIN_SERVICE, self.KEYCHAIN_ACCOUNT)
        path = self._fallback_token_path()
        if path.exists():
            path.unlink()
            return True
        return True

    def status(self) -> dict[str, Any]:
        tokens = self._load_stored_tokens()
        scopes = self._configured_scopes()
        configured = self.client_configured and tokens is not None
        account = None
        if tokens and tokens.get("account_email"):
            account = str(tokens["account_email"])
        location = (
            redact_token_location(self.KEYCHAIN_SERVICE, self.KEYCHAIN_ACCOUNT)
            if keychain.read_generic_password(self.KEYCHAIN_SERVICE, self.KEYCHAIN_ACCOUNT)
            else (
                f"file://{self._fallback_token_path()} (redacted)"
                if self._fallback_token_path().exists()
                else "not stored"
            )
        )
        return {
            "configured": configured,
            "client_configured": self.client_configured,
            "account_email": account,
            "scopes": scopes,
            "token_location": location,
            "gmail_enabled_flag": self.settings.nova_gmail_enabled,
        }

    def _configured_scopes(self) -> list[str]:
        scopes = [GMAIL_COMPOSE_SCOPE]
        if self.settings.nova_gmail_send_enabled:
            scopes.append(GMAIL_SEND_SCOPE)
        if self.settings.nova_gmail_readonly_enabled:
            scopes.append(GMAIL_READONLY_SCOPE)
        return scopes

    def _refresh_access_token(self, refresh_token: str) -> GmailTokenBundle | None:
        if not self.client_configured:
            return None
        data = {
            "client_id": self.settings.nova_gmail_client_id,
            "client_secret": self.settings.nova_gmail_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        with httpx.Client(timeout=15.0) as client:
            response = client.post(TOKEN_URL, data=data)
            if response.status_code >= 400:
                return None
            payload = response.json()
        access = str(payload.get("access_token", ""))
        if not access:
            return None
        return GmailTokenBundle(
            access_token=access,
            refresh_token=refresh_token,
            expires_in=payload.get("expires_in"),
            scope=str(payload.get("scope", "")),
            token_type=str(payload.get("token_type", "Bearer")),
            account_email=None,
        )

    def get_access_token(self) -> str | None:
        if not self.client_configured or not self.settings.nova_gmail_enabled:
            return None
        stored = self._load_stored_tokens()
        if not stored:
            return None
        refresh = stored.get("refresh_token")
        if isinstance(refresh, str) and refresh:
            bundle = self._refresh_access_token(refresh)
            if bundle is None:
                return None
            stored["access_token"] = bundle.access_token
            if bundle.account_email:
                stored["account_email"] = bundle.account_email
            self._save_tokens(stored)
            return bundle.access_token
        access = stored.get("access_token")
        return str(access) if access else None

    def start_auth_flow(self, *, redirect_port: int = 8765) -> int:
        if not self.client_configured:
            print(
                "Gmail OAuth is not configured.\n"
                "Set NOVA_GMAIL_CLIENT_ID and NOVA_GMAIL_CLIENT_SECRET, then run: nova gmail auth"
            )
            return 1
        state = secrets.token_urlsafe(16)
        redirect_uri = f"http://127.0.0.1:{redirect_port}/oauth2/callback"
        params = {
            "client_id": self.settings.nova_gmail_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self._configured_scopes()),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
        captured: dict[str, str] = {}

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                if parsed.path != "/oauth2/callback":
                    self.send_response(404)
                    self.end_headers()
                    return
                if query.get("state", [""])[0] != state:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"State mismatch")
                    return
                code = query.get("code", [""])[0]
                captured["code"] = code
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"NOVA Gmail auth complete. You can close this tab.")

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

        server = HTTPServer(("127.0.0.1", redirect_port), _Handler)
        thread = Thread(target=server.handle_request, daemon=True)
        thread.start()
        print(f"Opening browser for Gmail OAuth...\n{auth_url}")
        webbrowser.open(auth_url)
        thread.join(timeout=120)
        server.server_close()
        code = captured.get("code", "")
        if not code:
            print("OAuth flow did not return an authorization code.")
            return 1
        token_data = {
            "client_id": self.settings.nova_gmail_client_id,
            "client_secret": self.settings.nova_gmail_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post(TOKEN_URL, data=token_data)
            response.raise_for_status()
            payload = response.json()
        refresh = payload.get("refresh_token")
        access = payload.get("access_token")
        if not refresh and not access:
            print("Token response missing refresh_token and access_token.")
            return 1
        bundle: dict[str, Any] = {
            "refresh_token": refresh,
            "access_token": access,
            "scope": payload.get("scope", ""),
            "token_type": payload.get("token_type", "Bearer"),
        }
        if access:
            email = fetch_profile_email(str(access))
            if email:
                bundle["account_email"] = email
        self._save_tokens(bundle)
        print("Gmail OAuth connected. Run: nova gmail status")
        return 0
