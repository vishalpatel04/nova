"""Phase 3F controlled shell execution tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.models.orm import ApprovalRequest, AuditEvent, ShellExecution
from nova_core.shell.safe_command import sanitize_output_excerpt, validate_safe_shell_command


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "curl https://example.com",
        "source .env",
        "cat .env",
        "cat ~/.ssh/id_rsa",
        "ls ~/NOVA_VAULT",
        "bash -c ls",
        "python -c print(1)",
        "ls a; ls b",
        "ls a && ls b",
        "ls a | wc",
        "echo hi > /tmp/x",
        "echo $(pwd)",
        "echo `pwd`",
        "ls a\nls b",
    ],
)
def test_unsafe_commands_blocked_before_approval(command: str) -> None:
    result = validate_safe_shell_command(command)
    assert result.allowed is False
    assert result.blocked is True


def test_safe_commands_parse() -> None:
    for command in (
        "pwd",
        "ls",
        "ls ~/Projects/nova",
        "git status",
        "git diff --stat",
        "git log --oneline",
        "make lint",
    ):
        result = validate_safe_shell_command(command)
        assert result.allowed is True, command
        assert result.argv is not None


@pytest.mark.asyncio
async def test_chat_rm_hard_blocked_no_approval(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post("/api/v1/chat", json={"message": "run shell rm -rf /"})
    data = resp.json()
    assert data["blocked"] is True
    assert data.get("approval_required") is not True
    pending = await db_session.execute(select(ApprovalRequest))
    assert pending.scalars().all() == []


async def _shell_approval_flow(
    auth_client: AsyncClient,
    message: str,
) -> str:
    chat = await auth_client.post("/api/v1/chat", json={"message": message})
    assert chat.status_code == 200
    body = chat.json()
    assert body["approval_required"] is True
    approval_id = body["approval_id"]
    approve = await auth_client.post(f"/api/v1/approvals/{approval_id}/approve")
    assert approve.status_code == 200
    return approval_id


@pytest.mark.asyncio
async def test_pwd_executes_after_approval(auth_client: AsyncClient, paired_client_token) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    approval_id = await _shell_approval_flow(auth_client, "run shell pwd")
    exec_resp = await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    assert exec_resp.status_code == 200
    data = exec_resp.json()
    assert data["status"] == "succeeded"
    assert data["stdout_excerpt"]
    assert "sk-" not in data["stdout_excerpt"]


@pytest.mark.asyncio
async def test_safe_ls_executes_after_approval(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    approval_id = await _shell_approval_flow(auth_client, "run shell ls ~/Projects/nova")
    exec_resp = await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    assert exec_resp.status_code == 200
    assert exec_resp.json()["status"] == "succeeded"


@pytest.mark.asyncio
async def test_git_status_executes_after_approval(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    approval_id = await _shell_approval_flow(auth_client, "run shell git status")
    exec_resp = await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    assert exec_resp.status_code == 200
    assert exec_resp.json()["status"] in {"succeeded", "failed"}


@pytest.mark.asyncio
async def test_pending_approval_cannot_execute(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    chat = await auth_client.post("/api/v1/chat", json={"message": "run shell pwd"})
    approval_id = chat.json()["approval_id"]
    exec_resp = await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    assert exec_resp.status_code == 409


@pytest.mark.asyncio
async def test_rejected_approval_cannot_execute(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    chat = await auth_client.post("/api/v1/chat", json={"message": "run shell pwd"})
    approval_id = chat.json()["approval_id"]
    await auth_client.post(f"/api/v1/approvals/{approval_id}/reject")
    exec_resp = await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    assert exec_resp.status_code == 409


@pytest.mark.asyncio
async def test_expired_approval_cannot_execute(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    chat = await auth_client.post("/api/v1/chat", json={"message": "run shell pwd"})
    approval_id = chat.json()["approval_id"]
    await auth_client.post(f"/api/v1/approvals/{approval_id}/approve")
    record = await db_session.get(ApprovalRequest, approval_id)
    assert record is not None
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()
    exec_resp = await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    assert exec_resp.status_code == 409


@pytest.mark.asyncio
async def test_consumed_approval_replay_blocked(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    approval_id = await _shell_approval_flow(auth_client, "run shell pwd")
    first = await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    assert first.status_code == 200
    replay = await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    assert replay.status_code == 409


@pytest.mark.asyncio
async def test_fingerprint_mismatch_blocked_on_execute(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    chat = await auth_client.post("/api/v1/chat", json={"message": "run shell pwd"})
    approval_id = chat.json()["approval_id"]
    record = await db_session.get(ApprovalRequest, approval_id)
    assert record is not None
    record.action_fingerprint = "deadbeef"
    await db_session.commit()
    await auth_client.post(f"/api/v1/approvals/{approval_id}/approve")
    exec_resp = await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    assert exec_resp.status_code == 409


@pytest.mark.asyncio
async def test_execution_audit_events(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    approval_id = await _shell_approval_flow(auth_client, "run shell pwd")
    await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    actions = (
        (
            await db_session.execute(
                select(AuditEvent.action).where(AuditEvent.action.like("execution.%"))
            )
        )
        .scalars()
        .all()
    )
    assert "execution.requested" in actions
    assert "execution.started" in actions


def test_stdout_stderr_excerpt_bounded() -> None:
    secret = "sk-" + "a" * 40
    long_text = secret + "\n" + ("x" * 5000)
    excerpt = sanitize_output_excerpt(long_text, max_length=4096)
    assert "sk-" not in excerpt
    assert len(excerpt) <= 4096 + len("\n… (truncated)")


@pytest.mark.asyncio
async def test_concurrent_execution_reuse_blocked(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    approval_id = await _shell_approval_flow(auth_client, "run shell pwd")

    async def run_once() -> int:
        resp = await auth_client.post(
            "/api/v1/executions/run-approved",
            json={"approval_id": approval_id},
        )
        return resp.status_code

    results = await asyncio.gather(run_once(), run_once())
    assert 200 in results
    assert 409 in results
    rows = (
        (
            await db_session.execute(
                select(ShellExecution).where(ShellExecution.approval_id == approval_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_execution_record_persisted(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    approval_id = await _shell_approval_flow(auth_client, "run shell pwd")
    await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    rows = (await db_session.execute(select(ShellExecution))).scalars().all()
    assert len(rows) >= 1
    assert rows[0].approval_id == approval_id


@pytest.mark.asyncio
async def test_make_lint_executes_after_approval(
    auth_client: AsyncClient, paired_client_token
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    approval_id = await _shell_approval_flow(auth_client, "run shell make lint")
    exec_resp = await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    assert exec_resp.status_code == 200
    assert exec_resp.json()["status"] in {"succeeded", "failed"}


def test_symlink_escape_blocked(tmp_path) -> None:
    allowed = tmp_path / "safe"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside-secret")
    link = allowed / "escape-link"
    link.symlink_to(outside / "secret.txt")
    result = validate_safe_shell_command(
        f"cat {link}",
        allowed_roots=[str(allowed)],
    )
    assert result.allowed is False
    assert result.blocked is True


@pytest.mark.asyncio
async def test_audit_logs_do_not_contain_secrets(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    approval_id = await _shell_approval_flow(auth_client, "run shell pwd")
    await auth_client.post(
        "/api/v1/executions/run-approved",
        json={"approval_id": approval_id},
    )
    events = (
        (await db_session.execute(select(AuditEvent).where(AuditEvent.action.like("execution.%"))))
        .scalars()
        .all()
    )
    for event in events:
        blob = str(event.details)
        assert "sk-" not in blob.lower()
        assert "nova_cli_" not in blob
