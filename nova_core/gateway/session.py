"""Gateway session tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nova_core.gateway.channels import GatewayChannel


@dataclass
class GatewaySession:
    session_id: str
    user_id: str
    channel: GatewayChannel
    pending_approval: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class GatewaySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, GatewaySession] = {}

    def get_or_create(
        self,
        session_id: str,
        *,
        user_id: str,
        channel: GatewayChannel,
    ) -> GatewaySession:
        if session_id not in self._sessions:
            self._sessions[session_id] = GatewaySession(
                session_id=session_id,
                user_id=user_id,
                channel=channel,
            )
        return self._sessions[session_id]

    def set_pending_approval(self, session_id: str, kind: str | None) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.pending_approval = kind
