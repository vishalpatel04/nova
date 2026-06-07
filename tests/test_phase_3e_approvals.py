"""Phase 3E capability approval tests."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.approvals import ApprovalRequestService
from nova_core.auth.principal import Principal
from nova_core.capabilities.model import (
    ActionApprovalStatus,
    CapabilityName,
    compute_action_fingerprint,
)
from nova_core.models.orm import ApprovalRequest, AuditEvent
from nova_core.schemas.errors import ConflictError
from nova_core.tools.provider_security import scrub_runtime_detail


@pytest.mark.asyncio
async def test_shell_execute_creates_pending_approval_not_execution(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    resp = await auth_client.post("/api/v1/chat", json={"message": "run shell ls"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["blocked"] is False
    assert data["approval_required"] is True
    assert data["intent"] == "approval_required"
    assert "I can do this after approval" in data["response"]
    assert data["approval_id"]
    assert data["risk_level"] == "critical"

    record = await db_session.get(ApprovalRequest, data["approval_id"])
    assert record is not None
    assert record.status == ActionApprovalStatus.PENDING.value
    assert record.capability == CapabilityName.SHELL_EXECUTE.value
    assert record.device_id == device_id
    assert "ls" in record.command_or_payload_preview

    audit = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "approval.requested")
    )
    assert audit.scalars().first() is not None


@pytest.mark.asyncio
async def test_approve_requires_same_user_device_ownership(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    chat = await auth_client.post("/api/v1/chat", json={"message": "run shell ls"})
    approval_id = chat.json()["approval_id"]
    record = await db_session.get(ApprovalRequest, approval_id)
    assert record is not None

    approve = await auth_client.post(f"/api/v1/approvals/{approval_id}/approve")
    assert approve.status_code == 200

    svc = ApprovalRequestService(db_session)
    other = Principal(
        principal_type="device",
        principal_id="other-device",
        user_id=record.user_id,
        device_id="other-device",
        token_role="client",
    )
    from nova_core.schemas.errors import UnauthorizedError

    with pytest.raises(UnauthorizedError):
        await svc.get_owned(approval_id, other)


@pytest.mark.asyncio
async def test_one_time_approval_cannot_be_reused(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    chat = await auth_client.post("/api/v1/chat", json={"message": "run shell ls"})
    approval_id = chat.json()["approval_id"]
    record = await db_session.get(ApprovalRequest, approval_id)
    assert record is not None

    await auth_client.post(f"/api/v1/approvals/{approval_id}/approve")
    await db_session.refresh(record)

    svc = ApprovalRequestService(db_session)
    principal = Principal(
        principal_type="device",
        principal_id=_device_id,
        user_id=record.user_id,
        device_id=_device_id,
        token_role="client",
    )
    consumed = await svc.consume(
        principal,
        approval_id,
        expected_fingerprint=record.action_fingerprint,
    )
    assert consumed.status == ActionApprovalStatus.CONSUMED.value

    reuse = await auth_client.post(f"/api/v1/approvals/{approval_id}/approve")
    assert reuse.status_code == 409


@pytest.mark.asyncio
async def test_consumed_approval_cannot_be_consumed_twice(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    chat = await auth_client.post("/api/v1/chat", json={"message": "run shell ls"})
    approval_id = chat.json()["approval_id"]
    await auth_client.post(f"/api/v1/approvals/{approval_id}/approve")
    record = await db_session.get(ApprovalRequest, approval_id)
    assert record is not None

    svc = ApprovalRequestService(db_session)
    principal = Principal(
        principal_type="device",
        principal_id=_device_id,
        user_id=record.user_id,
        device_id=_device_id,
        token_role="client",
    )
    first = await svc.consume(
        principal,
        approval_id,
        expected_fingerprint=record.action_fingerprint,
    )
    assert first.status == ActionApprovalStatus.CONSUMED.value

    with pytest.raises(ConflictError, match="consumed"):
        await svc.consume(
            principal,
            approval_id,
            expected_fingerprint=record.action_fingerprint,
        )


@pytest.mark.asyncio
async def test_expired_approval_cannot_be_approved(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    chat = await auth_client.post("/api/v1/chat", json={"message": "run shell ls"})
    approval_id = chat.json()["approval_id"]
    record = await db_session.get(ApprovalRequest, approval_id)
    assert record is not None
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    expired = await auth_client.post(f"/api/v1/approvals/{approval_id}/approve")
    assert expired.status_code == 409


@pytest.mark.asyncio
async def test_protected_path_still_blocked_without_approval(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    resp = await auth_client.post("/api/v1/chat", json={"message": "read file ~/.ssh/id_rsa"})
    data = resp.json()
    assert data["blocked"] is True
    assert data.get("approval_required") is not True
    assert "Blocked:" in data["response"]

    pending = await auth_client.get("/api/v1/approvals/pending")
    assert pending.json()["items"] == []


@pytest.mark.asyncio
async def test_write_file_creates_approval_request(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    resp = await auth_client.post(
        "/api/v1/chat", json={"message": "write file ~/Projects/nova/test.txt"}
    )
    data = resp.json()
    assert data["approval_required"] is True
    assert data["risk_level"] == "high"


@pytest.mark.asyncio
async def test_pending_approvals_api_returns_only_own(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    await auth_client.post("/api/v1/chat", json={"message": "run shell ls"})
    pending = await auth_client.get("/api/v1/approvals/pending")
    assert pending.status_code == 200
    items = pending.json()["items"]
    assert len(items) >= 1
    assert all(item["status"] == "pending" for item in items)


@pytest.mark.asyncio
async def test_cloud_send_file_requires_approval_message() -> None:
    from nova_core.capabilities.resolver import cloud_file_resolution

    resolution = cloud_file_resolution("~/Projects/nova/README.md")
    assert resolution.capability == CapabilityName.CLOUD_SEND_FILE
    assert resolution.kind == "approval"


@pytest.mark.asyncio
async def test_runtime_status_scrubs_secrets() -> None:
    detail = scrub_runtime_detail("sk-secret-key-value")
    assert detail is not None
    assert "sk-secret" not in detail


@pytest.mark.asyncio
async def test_fingerprint_mismatch_blocks_consume(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    chat = await auth_client.post("/api/v1/chat", json={"message": "run shell ls"})
    approval_id = chat.json()["approval_id"]
    await auth_client.post(f"/api/v1/approvals/{approval_id}/approve")

    svc = ApprovalRequestService(db_session)
    principal = Principal(
        principal_type="device",
        principal_id=device_id,
        user_id=(await db_session.get(ApprovalRequest, approval_id)).user_id,
        device_id=device_id,
        token_role="client",
    )
    with pytest.raises(Exception):
        await svc.consume(
            principal,
            approval_id,
            expected_fingerprint=compute_action_fingerprint("shell.execute", {"command": "rm"}),
        )


@pytest.mark.asyncio
async def test_reject_approval_audit(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    chat = await auth_client.post("/api/v1/chat", json={"message": "run shell ls"})
    approval_id = chat.json()["approval_id"]
    await auth_client.post(f"/api/v1/approvals/{approval_id}/reject")

    audit = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == "approval.rejected")
    )
    assert audit.scalars().first() is not None
