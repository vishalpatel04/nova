"""Orbit email draft orchestration for chat."""

from __future__ import annotations

import uuid
from typing import Any

from nova_core.agent_os.mission import AgentMissionRunner
from nova_core.orbit.chat_payload import build_orbit_email_chat_payload
from nova_core.orbit.email_draft import (
    EmailDraft,
    EmailDraftStore,
    build_investor_update_email,
    try_create_gmail_draft,
)
from nova_core.orbit.email_intent import EmailDraftRequest
from nova_core.schemas.settings import Settings


class OrbitEmailService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = EmailDraftStore()
        self._mission_runner = AgentMissionRunner()

    def latest_awaiting_send(self) -> EmailDraft | None:
        return self.store.latest_awaiting_send()

    def get_draft(self, draft_id: str) -> EmailDraft | None:
        return self.store.load(draft_id)

    def _latest_mission_context(self) -> dict[str, Any]:
        mission = self._mission_runner.latest_awaiting_approval()
        if mission is None:
            ids = self._mission_runner.store.list_ids()
            for mission_id in reversed(ids):
                candidate = self._mission_runner.store.load(mission_id)
                if candidate is not None:
                    mission = candidate
                    break
        if mission is None:
            return {}
        report = mission.final_report
        return {
            "app_name": report.get("app_name", mission.artifacts.get("app_name")),
            "preview_url": mission.preview_url or report.get("preview_url"),
            "mission_id": mission.mission_id,
        }

    def create_draft(self, request: EmailDraftRequest) -> EmailDraft:
        context = self._latest_mission_context()
        topic = request.topic
        if request.kind == "investor_update":
            topic = context.get("app_name") or topic
        to, subject, body = build_investor_update_email(
            topic=topic,
            recipient=request.recipient,
            preview_url=context.get("preview_url"),
            app_name=context.get("app_name"),
        )
        source, gmail_id = try_create_gmail_draft(
            to=to,
            subject=subject,
            body=body,
            gmail_enabled=self.settings.nova_gmail_enabled,
        )
        draft = EmailDraft(
            draft_id=str(uuid.uuid4()),
            to=to,
            subject=subject,
            body=body,
            source=source,
            status="awaiting_send_approval",
            evidence_path="",
            gmail_draft_id=gmail_id,
            metadata={
                "raw_request": request.raw_text,
                "mission_id": context.get("mission_id"),
            },
        )
        self.store.save(draft)
        return draft

    def approve_send(self, draft_id: str | None = None) -> EmailDraft:
        draft = self._resolve_draft(draft_id)
        draft.status = "send_approved"
        self.store.save(draft)
        return draft

    def skip_send(self, draft_id: str | None = None) -> EmailDraft:
        draft = self._resolve_draft(draft_id)
        draft.status = "skipped"
        self.store.save(draft)
        return draft

    def payload_for(self, draft: EmailDraft) -> dict[str, Any]:
        return build_orbit_email_chat_payload(draft)

    def _resolve_draft(self, draft_id: str | None) -> EmailDraft:
        if draft_id:
            draft = self.store.load(draft_id)
            if draft is None:
                raise ValueError(f"Email draft not found: {draft_id}")
            return draft
        draft = self.latest_awaiting_send()
        if draft is None:
            raise ValueError("No email draft is awaiting send approval.")
        return draft
