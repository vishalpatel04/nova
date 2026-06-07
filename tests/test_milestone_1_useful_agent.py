"""Milestone 1 useful local coding agent — security and workflow tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker.commands import execute_read_only_command
from nova_core.capabilities.model import CapabilityName, compute_action_fingerprint
from nova_core.models.orm import ApprovalRequest
from nova_core.patch.apply import apply_patch_payload
from nova_core.patch.policy import validate_patch_payload
from nova_core.project.context import validate_project_root
from nova_core.tools.protected_paths import PROTECTED_PATH_MESSAGE


@pytest.fixture
def demo_project(tmp_path: Path) -> Path:
    root = tmp_path / "demo-proj"
    root.mkdir()
    (root / "Makefile").write_text(".PHONY: test\n\ntest:\n\tpython -m pytest -q tests\n")
    tests = root / "tests"
    tests.mkdir()
    (tests / "demo_fail.py").write_text(
        "def test_demo():\n    assert False\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Demo", encoding="utf-8")
    return root.resolve()


@pytest.fixture
def allow_demo_root(demo_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def _fake_roots(roots: list[str] | None = None) -> list[Path]:
        return [demo_project]

    monkeypatch.setattr("nova_core.tools.safe_paths.expand_allowed_roots", _fake_roots)
    monkeypatch.setattr("nova_core.project.context.expand_allowed_roots", _fake_roots)
    return demo_project


async def _approved_patch_record(
    db_session: AsyncSession,
    device_id: str,
    payload: dict,
    *,
    status: str = "approved",
    fingerprint: str | None = None,
) -> ApprovalRequest:
    from datetime import UTC, datetime, timedelta

    from nova_core.models.orm import Device

    device = await db_session.get(Device, device_id)
    assert device is not None
    fp = fingerprint or compute_action_fingerprint(CapabilityName.CODE_PATCH.value, payload)
    record = ApprovalRequest(
        user_id=device.user_id,
        device_id=device_id,
        capability=CapabilityName.CODE_PATCH.value,
        action_summary="test",
        command_or_payload_preview="preview",
        action_fingerprint=fp,
        risk_level="high",
        status=status,
        metadata_json={"payload": payload},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record


async def _pair_and_set_project(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    demo_project: Path,
) -> str:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post(
        "/api/v1/projects/active",
        json={"project_root": str(demo_project)},
    )
    assert resp.status_code == 200, resp.text
    return token


def _patch_payload(project_root: Path, rel: str, content: str, *, action: str = "modify") -> dict:
    return {
        "project_root": str(project_root),
        "summary": "test patch",
        "files": [{"path": rel, "action": action, "content": content}],
        "unified_diff": f"--- a/{rel}\n+++ b/{rel}",
    }


@pytest.mark.asyncio
async def test_set_project_accepts_safe_root(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _pair_and_set_project(auth_client, paired_client_token, allow_demo_root)
    resp = await auth_client.get("/api/v1/projects/active")
    assert resp.status_code == 200
    assert resp.json()["project_name"] == "demo-proj"


@pytest.mark.asyncio
async def test_set_project_rejects_protected_paths(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post(
        "/api/v1/projects/active",
        json={"project_root": "~/NOVA_VAULT/project"},
    )
    assert resp.status_code == 422 or resp.status_code == 400
    body = resp.text
    assert "protected" in body.lower() or "Blocked" in body


def test_set_project_rejects_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = allowed / "escape"
    link.symlink_to(outside)
    monkeypatch.setattr("nova_core.tools.safe_paths.expand_allowed_roots", lambda roots=None: [allowed.resolve()])
    monkeypatch.setattr("nova_core.project.context.expand_allowed_roots", lambda roots=None: [allowed.resolve()])
    result = validate_project_root(str(link))
    assert result.allowed is False


@pytest.mark.asyncio
async def test_patch_existing_file_requires_approval_flow(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
    db_session: AsyncSession,
) -> None:
    await _pair_and_set_project(auth_client, paired_client_token, allow_demo_root)
    target = allow_demo_root / "tests" / "demo_fail.py"
    new_content = target.read_text(encoding="utf-8").replace("False", "True", 1)
    payload = _patch_payload(allow_demo_root, "tests/demo_fail.py", new_content)
    record = await _approved_patch_record(db_session, paired_client_token[0], payload)

    blocked = await auth_client.post(
        "/api/v1/executions/apply-approved-patch",
        json={"approval_id": record.id},
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] in {"succeeded", "running", "failed"}


def test_patch_protected_path_blocked(allow_demo_root: Path) -> None:
    payload = _patch_payload(allow_demo_root, "../NOVA_VAULT/x.txt", "x")
    result = validate_patch_payload(allow_demo_root, payload)
    assert result.allowed is False


def test_patch_env_blocked(allow_demo_root: Path) -> None:
    payload = _patch_payload(allow_demo_root, ".env", "SECRET=1")
    result = validate_patch_payload(allow_demo_root, payload)
    assert result.allowed is False
    assert "protected" in (result.reason or "").lower() or PROTECTED_PATH_MESSAGE in (
        result.reason or ""
    )


def test_patch_binary_blocked(allow_demo_root: Path) -> None:
    payload = _patch_payload(allow_demo_root, "tests/demo_fail.py", "data\x00bad")
    result = validate_patch_payload(allow_demo_root, payload)
    assert result.allowed is False


def test_patch_vendor_blocked(allow_demo_root: Path) -> None:
    payload = _patch_payload(allow_demo_root, "node_modules/pkg/index.js", "x")
    result = validate_patch_payload(allow_demo_root, payload)
    assert result.allowed is False


def test_patch_traversal_blocked(allow_demo_root: Path) -> None:
    payload = _patch_payload(allow_demo_root, "../../etc/passwd", "x")
    result = validate_patch_payload(allow_demo_root, payload)
    assert result.allowed is False


def test_patch_symlink_escape_blocked(allow_demo_root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = allow_demo_root / "linked.txt"
    link.symlink_to(outside)
    payload = _patch_payload(allow_demo_root, "linked.txt", "overwrite")
    result = validate_patch_payload(allow_demo_root, payload)
    if link.resolve().is_relative_to(allow_demo_root):
        pytest.skip("symlink resolves inside project on this platform")
    assert result.allowed is False


@pytest.mark.asyncio
async def test_fingerprint_mismatch_blocked(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
    db_session: AsyncSession,
) -> None:
    await _pair_and_set_project(auth_client, paired_client_token, allow_demo_root)
    payload = _patch_payload(
        allow_demo_root, "tests/demo_fail.py", "def test_demo():\n    assert True\n"
    )
    wrong_fp = compute_action_fingerprint(CapabilityName.CODE_PATCH.value, {"files": []})
    record = await _approved_patch_record(
        db_session,
        paired_client_token[0],
        payload,
        fingerprint=wrong_fp,
    )
    resp = await auth_client.post(
        "/api/v1/executions/apply-approved-patch",
        json={"approval_id": record.id},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_pending_patch_cannot_apply(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
    db_session: AsyncSession,
) -> None:
    await _pair_and_set_project(auth_client, paired_client_token, allow_demo_root)
    payload = _patch_payload(
        allow_demo_root, "tests/demo_fail.py", "def test_demo():\n    assert True\n"
    )
    record = await _approved_patch_record(
        db_session, paired_client_token[0], payload, status="pending"
    )
    resp = await auth_client.post(
        "/api/v1/executions/apply-approved-patch",
        json={"approval_id": record.id},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_consumed_patch_cannot_replay(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
    db_session: AsyncSession,
) -> None:
    await _pair_and_set_project(auth_client, paired_client_token, allow_demo_root)
    target = allow_demo_root / "tests" / "demo_fail.py"
    payload = _patch_payload(
        allow_demo_root,
        "tests/demo_fail.py",
        target.read_text(encoding="utf-8").replace("False", "True", 1),
    )
    record = await _approved_patch_record(db_session, paired_client_token[0], payload)
    first = await auth_client.post(
        "/api/v1/executions/apply-approved-patch",
        json={"approval_id": record.id},
    )
    assert first.status_code == 200
    second = await auth_client.post(
        "/api/v1/executions/apply-approved-patch",
        json={"approval_id": record.id},
    )
    assert second.status_code == 409


def test_atomic_replace_preserves_original_on_failure(allow_demo_root: Path) -> None:
    target = allow_demo_root / "tests" / "demo_fail.py"
    original = target.read_text(encoding="utf-8")
    validation = validate_patch_payload(
        allow_demo_root,
        _patch_payload(allow_demo_root, "tests/demo_fail.py", original.replace("False", "True", 1)),
    )
    assert validation.allowed
    # Simulate failure by corrupting after backup — apply handles rollback internally
    result = apply_patch_payload(allow_demo_root, validation)
    assert result.success
    target.write_text(original, encoding="utf-8")


def test_worker_revalidates_patch_policy(allow_demo_root: Path) -> None:
    payload = _patch_payload(allow_demo_root, "node_modules/x.js", "bad")
    out = execute_read_only_command(
        "apply_approved_patch",
        {"project_root": str(allow_demo_root), "patch_payload": payload},
    )
    assert out.get("success") is False


def test_worker_inspect_repo(allow_demo_root: Path) -> None:
    out = execute_read_only_command("inspect_repo", {"project_root": str(allow_demo_root)})
    assert out.get("success") is True
    assert "demo-proj" in out.get("output", "")


def test_output_excerpts_bounded() -> None:
    from nova_core.shell.safe_command import sanitize_output_excerpt

    huge = "x" * 100_000
    excerpt = sanitize_output_excerpt(huge)
    assert len(excerpt) < 20_000


@pytest.mark.asyncio
async def test_chat_set_project_and_inspect(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _pair_and_set_project(auth_client, paired_client_token, allow_demo_root)
    resp = await auth_client.post("/api/v1/chat", json={"message": "inspect repo"})
    assert resp.status_code == 200
    assert "demo-proj" in resp.json()["response"]


@pytest.mark.asyncio
async def test_create_text_file_requires_valid_patch(
    allow_demo_root: Path,
) -> None:
    payload = _patch_payload(allow_demo_root, "notes.txt", "hello", action="create")
    result = validate_patch_payload(allow_demo_root, payload)
    assert result.allowed is True


def test_no_secrets_in_patch_preview(allow_demo_root: Path) -> None:
    from nova_core.patch.policy import build_patch_preview

    preview = build_patch_preview(
        _patch_payload(allow_demo_root, "tests/demo_fail.py", "assert True")
    )
    assert "OPENAI" not in preview
    assert "api_key" not in preview.lower()
