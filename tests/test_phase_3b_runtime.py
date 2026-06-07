"""Phase 3B integrated runtime tests."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.orm import AuditEvent, AutomationRun, ChatMessageRecord, ChatSession


async def _pair_other_client(auth_client: AsyncClient) -> str:
    device_id = f"test-client-{uuid.uuid4().hex[:8]}"
    auth_client.headers["Authorization"] = "Bearer nova_bts_test_admin"
    create_resp = await auth_client.post(
        "/api/v1/pairing/codes",
        json={"device_type": "iphone_client", "proposed_device_id": device_id},
    )
    assert create_resp.status_code == 201, create_resp.text
    code = create_resp.json()["code"]
    claim = await auth_client.post(
        "/api/v1/pairing/claim",
        json={
            "code": code,
            "device_id": device_id,
            "name": "Other Client",
            "device_type": "iphone_client",
        },
        headers={k: v for k, v in auth_client.headers.items() if k.lower() != "authorization"},
    )
    assert claim.status_code == 200, claim.text
    if claim.json().get("status") in ("pending", "pending_approval"):
        pairing_id = create_resp.json()["pairing_id"]
        await auth_client.post(f"/api/v1/pairing/{pairing_id}/approve")
        token_resp = await auth_client.post(
            f"/api/v1/pairing/{pairing_id}/token",
            json={"device_id": device_id},
        )
        assert token_resp.status_code == 200, token_resp.text
        return token_resp.json()["token"]
    return claim.json()["token"]


@pytest.mark.asyncio
async def test_general_chat_persists_session_and_usage(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    resp = await auth_client.post("/api/v1/chat", json={"message": "Explain NOVA briefly"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    assert body["token_usage"]["provider"] in {"local", "qwen"}
    assert body["blocked"] is False

    session_result = await db_session.execute(
        select(ChatSession).where(ChatSession.id == body["session_id"])
    )
    assert session_result.scalar_one_or_none() is not None
    messages = await db_session.execute(
        select(ChatMessageRecord).where(ChatMessageRecord.session_id == body["session_id"])
    )
    assert len(messages.scalars().all()) == 2

    restored = await auth_client.get(f"/api/v1/chat/sessions/{body['session_id']}")
    assert restored.status_code == 200
    assert len(restored.json()["messages"]) == 2


@pytest.mark.asyncio
async def test_runtime_status_keeps_paid_providers_disabled_by_default(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    resp = await auth_client.get("/api/v1/runtime/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["local_first"] is True
    assert body["paid_providers_enabled"] is False
    paid = [p for p in body["providers"] if p["paid"]]
    assert paid
    assert all(p["configured"] is False for p in paid)


@pytest.mark.asyncio
async def test_automation_execute_requires_approval_and_audits(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    resp = await auth_client.post(
        "/api/v1/automation/execute",
        json={"provider": "n8n", "action": "send_email", "payload": {"to": "x@example.com"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["requires_approval"] is True

    runs = await db_session.execute(select(AutomationRun).where(AutomationRun.id == body["id"]))
    assert runs.scalar_one_or_none() is not None
    audits = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "automation.execute")
    )
    assert audits.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_automation_dry_run_and_schedule(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    dry_run = await auth_client.post(
        "/api/v1/automation/execute",
        json={
            "provider": "n8n",
            "action": "dry_run",
            "payload": {"workflow": "demo"},
            "dry_run": True,
        },
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["status"] == "completed"

    create = await auth_client.post(
        "/api/v1/automation/schedules",
        json={
            "title": "Morning status",
            "provider": "n8n",
            "action": "status",
            "schedule": "0 9 * * *",
            "payload": {},
        },
    )
    assert create.status_code == 201
    assert create.json()["status"] == "paused"

    listed = await auth_client.get("/api/v1/automation/schedules")
    assert listed.status_code == 200
    assert any(task["title"] == "Morning status" for task in listed.json())


@pytest.mark.asyncio
async def test_automation_schedules_are_device_scoped(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_a, token_a = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token_a}"

    create = await auth_client.post(
        "/api/v1/automation/schedules",
        json={
            "title": "Device A schedule",
            "provider": "n8n",
            "action": "status",
            "schedule": "0 9 * * *",
            "payload": {},
        },
    )
    assert create.status_code == 201, create.text

    token_b = await _pair_other_client(auth_client)
    auth_client.headers["Authorization"] = f"Bearer {token_b}"

    listed = await auth_client.get("/api/v1/automation/schedules")
    assert listed.status_code == 200
    assert all(task["title"] != "Device A schedule" for task in listed.json())


@pytest.mark.asyncio
async def test_companion_prompt_creates_session(
    auth_client: AsyncClient, paired_client_token
) -> None:
    device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    resp = await auth_client.post(
        "/api/v1/companion/prompts",
        json={"message": "Run status from phone", "target_device_id": device_id},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["session_id"]
    assert body["message_id"]


@pytest.mark.asyncio
async def test_companion_prompt_rejects_unknown_target(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    resp = await auth_client.post(
        "/api/v1/companion/prompts",
        json={"message": "Run status", "target_device_id": "missing-device"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_companion_prompt_requires_target_device_id(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    resp = await auth_client.post(
        "/api/v1/companion/prompts",
        json={"message": "Run status"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_automation_runtime_does_not_execute_n8n_webhook() -> None:
    from nova_core.automation.base import AutomationProviderKind
    from nova_core.automation.runtime import AutomationRequest, AutomationRuntime
    from nova_core.schemas.settings import Settings

    runtime = AutomationRuntime(Settings(nova_n8n_base_url="http://example.invalid/webhook"))
    result = await runtime.execute(
        AutomationRequest(
            provider=AutomationProviderKind.N8N,
            action="send_email",
            payload={"to": "x@example.com"},
            approved=True,
        )
    )
    assert result.success is False
    assert result.error is not None
    assert "Phase 3B" in result.error


@pytest.mark.asyncio
async def test_chat_rejects_unknown_session_id(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    resp = await auth_client.post(
        "/api/v1/chat",
        json={"message": "help", "session_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_code_runtime_chat_commands(auth_client: AsyncClient, paired_client_token) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    analysis = await auth_client.post("/api/v1/chat", json={"message": "repo analysis"})
    assert analysis.status_code == 200
    assert analysis.json()["blocked"] is False
    assert "Python: yes" in analysis.json()["response"]

    explain = await auth_client.post(
        "/api/v1/chat", json={"message": "explain code ~/Projects/nova/README.md"}
    )
    assert explain.status_code == 200
    assert explain.json()["blocked"] is False

    patch = await auth_client.post(
        "/api/v1/chat", json={"message": "generate patch change the API"}
    )
    assert patch.status_code == 200
    assert patch.json()["approval_required"] is True
