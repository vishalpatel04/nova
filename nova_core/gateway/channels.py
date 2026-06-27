"""NOVA Gateway channel definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GatewayChannel(StrEnum):
    MACOS_CHAT = "macos_chat"
    CLI = "cli"
    VOICE = "voice"
    FUTURE_TELEGRAM = "future_telegram"
    FUTURE_WHATSAPP = "future_whatsapp"
    FUTURE_EMAIL = "future_email"


@dataclass
class GatewayMessage:
    channel: GatewayChannel
    user_id: str
    session_id: str
    text: str
    attachments: list[str] = field(default_factory=list)
    approval_context: dict[str, Any] = field(default_factory=dict)
    reply_target: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel.value,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "text": self.text,
            "attachments": self.attachments,
            "approval_context": self.approval_context,
            "reply_target": self.reply_target,
            "metadata": self.metadata,
        }
