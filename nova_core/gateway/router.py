"""NOVA Gateway router — channels in, Agent OS out. No untrusted skill execution."""

from __future__ import annotations

from typing import Any

from nova_core.gateway.channels import GatewayChannel, GatewayMessage
from nova_core.gateway.session import GatewaySessionStore

# OpenClaw skills/plugins are NOT executed by NOVA.
# See docs/OPENCLAW_INTEGRATION.md for security stance.


class GatewayRouter:
    """Route inbound channel messages to NOVA chat handlers."""

    def __init__(self, store: GatewaySessionStore | None = None) -> None:
        self.store = store or GatewaySessionStore()

    def normalize(self, message: GatewayMessage) -> dict[str, Any]:
        session = self.store.get_or_create(
            message.session_id,
            user_id=message.user_id,
            channel=message.channel,
        )
        return {
            "text": message.text.strip(),
            "session_id": message.session_id,
            "channel": message.channel.value,
            "user_id": message.user_id,
            "pending_approval": session.pending_approval,
            "attachments": message.attachments,
            "metadata": message.metadata,
        }

    def route_channel(self, channel: str) -> GatewayChannel:
        try:
            return GatewayChannel(channel)
        except ValueError:
            return GatewayChannel.CLI

    def openclaw_reference_only(self) -> dict[str, str]:
        return {
            "mode": "reference_only",
            "skill_execution": "disabled",
            "reason": "Untrusted OpenClaw/ClawHub skills require Sentry review and allowlisting.",
        }
