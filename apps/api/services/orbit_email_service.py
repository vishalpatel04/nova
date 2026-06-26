"""Orbit email draft orchestration for chat."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from apps.api.services.gmail_draft_service import GmailDraftService
from nova_core.agent_os.mission import AgentMissionRunner
from nova_core.orbit.chat_payload import build_orbit_email_chat_payload
from nova_core.orbit.contact_resolver import ContactResolution, resolve_contact, save_contact_alias
from nova_core.orbit.email_composer import EmailComposition, compose_email
from nova_core.orbit.email_draft import EmailDraft, EmailDraftStore
from nova_core.orbit.email_intent import EmailDraftRequest, EmailEditRequest
from nova_core.schemas.settings import Settings


@dataclass(frozen=True)
class EmailDraftOutcome:
    kind: str
    message: str
    draft: EmailDraft | None = None


class OrbitEmailService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = EmailDraftStore()
        self._mission_runner = AgentMissionRunner()
        self._gmail = GmailDraftService(settings)

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
            "mission_summary": report.get("app_spec_summary") or report.get("summary"),
        }

    def _resolve_recipient(self, recipient: str | None) -> ContactResolution:
        return resolve_contact(recipient)

    async def prepare_draft(
        self,
        request: EmailDraftRequest,
    ) -> EmailDraftOutcome:
        resolution = self._resolve_recipient(request.recipient)
        if resolution.ambiguous and not resolution.email:
            question = "Who should receive this email? Reply with a name or email address."
            if resolution.display_name:
                question = (
                    f"I couldn't resolve an email for {resolution.display_name}. "
                    "What email address should I use?"
                )
            return EmailDraftOutcome(kind="need_recipient", message=question)
        recipient_email = resolution.email
        return EmailDraftOutcome(
            kind="ready",
            message="",
            draft=await self._create_draft_record(request, recipient_email, resolution),
        )

    async def create_draft_from_recipient_reply(
        self,
        *,
        raw_request: str,
        topic: str,
        kind: str,
        purpose: str,
        recipient_text: str,
    ) -> EmailDraft:
        resolution = self._resolve_recipient(recipient_text)
        email = resolution.email
        if not email and "@" in recipient_text:
            email = recipient_text.strip()
        if not email:
            email = f"{recipient_text.strip().lower().replace(' ', '')}@example.com"
        if resolution.display_name and email and "@" in email:
            save_contact_alias(resolution.display_name or recipient_text, email)
        request = EmailDraftRequest(
            raw_text=raw_request,
            recipient=email,
            topic=topic,
            kind=kind,
            purpose=purpose,
        )
        return await self._create_draft_record(request, email, resolution)

    async def _create_draft_record(
        self,
        request: EmailDraftRequest,
        recipient_email: str | None,
        resolution: ContactResolution,
    ) -> EmailDraft:
        context = self._latest_mission_context()
        topic = request.topic
        if request.kind == "investor_update" or topic.lower() in {"this app", "the app"}:
            topic = str(context.get("app_name") or topic)
        composition = await compose_email(
            self.settings,
            purpose=request.purpose,
            recipient=recipient_email,
            topic=topic,
            preview_url=context.get("preview_url"),
            app_name=context.get("app_name"),
            mission_summary=context.get("mission_summary"),
        )
        source = "local"
        gmail_id: str | None = None
        if self._gmail.is_configured() and self.settings.nova_gmail_enabled:
            try:
                source, gmail_id = self._gmail.create_draft(
                    to=composition.to,
                    subject=composition.subject,
                    body=composition.body,
                )
            except Exception:
                source = "local"
                gmail_id = None
        draft = EmailDraft(
            draft_id=str(uuid.uuid4()),
            to=composition.to,
            subject=composition.subject,
            body=composition.body,
            source=source,
            status="awaiting_send_approval",
            evidence_path="",
            gmail_draft_id=gmail_id,
            metadata={
                "raw_request": request.raw_text,
                "mission_id": context.get("mission_id"),
                "attachments": composition.attachments,
                "contact_source": resolution.source,
                "purpose": request.purpose,
            },
        )
        self.store.save(draft)
        return draft

    async def edit_draft(self, draft_id: str | None, edit: EmailEditRequest) -> EmailDraft:
        draft = self._resolve_draft(draft_id)
        context = self._latest_mission_context()
        existing = EmailComposition(
            to=draft.to,
            subject=draft.subject,
            body=draft.body,
            attachments=list(draft.metadata.get("attachments") or []),
        )
        composition = await compose_email(
            self.settings,
            purpose=str(draft.metadata.get("purpose", "general")),
            recipient=draft.to,
            topic=draft.subject,
            preview_url=context.get("preview_url"),
            app_name=context.get("app_name"),
            mission_summary=context.get("mission_summary"),
            edit_instruction=edit.instruction,
            existing=existing,
        )
        draft.subject = composition.subject
        draft.body = composition.body
        draft.metadata["attachments"] = composition.attachments
        draft.status = "awaiting_send_approval"
        if draft.gmail_draft_id and self._gmail.is_configured():
            try:
                source, gmail_id = self._gmail.create_draft(
                    to=draft.to,
                    subject=draft.subject,
                    body=draft.body,
                )
                draft.source = source
                draft.gmail_draft_id = gmail_id
            except Exception:
                pass
        self.store.save(draft)
        return draft

    def approve_send(self, draft_id: str | None = None) -> tuple[EmailDraft, str]:
        draft = self._resolve_draft(draft_id)
        evidence = ""
        if self._gmail.is_configured() and self.settings.nova_gmail_enabled:
            try:
                if draft.gmail_draft_id:
                    result = self._gmail.send_draft(draft_id=draft.gmail_draft_id)
                else:
                    result = self._gmail.send_message(
                        to=draft.to,
                        subject=draft.subject,
                        body=draft.body,
                    )
                draft.status = "sent"
                message_id = result.get("id", "")
                evidence = (
                    f"Gmail message id: {message_id}" if message_id else "Gmail send completed."
                )
                draft.metadata["send_evidence"] = evidence
            except Exception as exc:
                draft.status = "send_approved"
                evidence = f"Gmail send failed: {exc.__class__.__name__}. Draft preserved locally."
        else:
            draft.status = "send_approved"
            evidence = "Gmail is not connected — cannot send automatically. Local draft preserved."
        self.store.save(draft)
        return draft, evidence

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

    # Back-compat sync wrapper for tests/scripts without an event loop.
    def create_draft(self, request: EmailDraftRequest) -> EmailDraft:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            raise RuntimeError("Use await prepare_draft() inside async context.")
        outcome = asyncio.run(self.prepare_draft(request))
        if outcome.kind == "need_recipient":
            raise ValueError(outcome.message)
        if outcome.draft is None:
            raise ValueError("Could not create email draft.")
        return outcome.draft
