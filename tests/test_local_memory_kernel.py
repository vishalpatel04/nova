"""Tests for NOVA local memory kernel."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.memory_kernel import MemoryKernelService
from nova_core.memory.access_policy import AccessProfile, resolve_access_policy
from nova_core.memory.vault import is_vault_path, sanitize_for_external_response
from nova_core.models.orm import MemoryFact, User
from nova_core.schemas.settings import Settings


@pytest.fixture
async def memory_user(db_session: AsyncSession) -> User:
    user = User(id="memory-test-user", display_name="Memory Test")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def memory_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    (home / "Documents").mkdir()
    (home / "Documents" / "lund.txt").write_text("Sweden exchange notes", encoding="utf-8")
    (home / "Downloads").mkdir()
    (home / "Downloads" / "reimbursement.pdf").write_bytes(b"%PDF-1.4")
    vault = home / "NOVA_VAULT"
    vault.mkdir()
    (vault / "secret.txt").write_text("top secret", encoding="utf-8")
    return home


def test_vault_path_blocked_direct() -> None:
    path = str(Path.home() / "NOVA_VAULT" / "secret.txt")
    assert is_vault_path(path) or is_vault_path("~/NOVA_VAULT/secret.txt")


def test_vault_file_url_blocked() -> None:
    assert is_vault_path("file:///Users/me/NOVA_VAULT/hidden.doc")


def test_vault_sanitize_never_leaks_filename() -> None:
    redacted = sanitize_for_external_response(str(Path.home() / "NOVA_VAULT" / "secret.txt"))
    assert "secret" not in redacted
    assert "vault" in redacted.lower() or "redacted" in redacted.lower()


def test_broad_local_policy_allows_home_subfolders(
    memory_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nova_core.memory.access_policy.Path.home", lambda: memory_home)
    policy = resolve_access_policy(profile=AccessProfile.BROAD_LOCAL)
    assert policy.is_path_allowed(str(memory_home / "Documents" / "lund.txt"))
    assert not policy.is_path_allowed(str(memory_home / "NOVA_VAULT" / "secret.txt"))


def test_custom_profile_include_exclude(memory_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nova_core.memory.access_policy.Path.home", lambda: memory_home)
    docs = str(memory_home / "Documents")
    dl = str(memory_home / "Downloads")
    policy = resolve_access_policy(
        profile=AccessProfile.CUSTOM,
        include_paths=[docs],
        exclude_paths=[dl],
    )
    assert policy.is_path_allowed(str(memory_home / "Documents" / "lund.txt"))
    assert not policy.is_path_allowed(str(memory_home / "Downloads" / "reimbursement.pdf"))


@pytest.mark.asyncio
async def test_remember_and_retrieve_fact(
    db_session: AsyncSession, test_settings: Settings, memory_user: User
) -> None:
    svc = MemoryKernelService(db_session, test_settings)
    fact = await svc.remember_fact(
        memory_user.id,
        subject="lund exchange documents",
        predicate="stored_in",
        object_summary="Downloads",
        user_confirmed=True,
    )
    result = await svc.retrieve(memory_user.id, "lund exchange")
    assert fact.id
    assert any("lund" in h.summary.lower() or "downloads" in h.summary.lower() for h in result.hits)


@pytest.mark.asyncio
async def test_forget_topic_removes_facts(
    db_session: AsyncSession, test_settings: Settings, memory_user: User
) -> None:
    svc = MemoryKernelService(db_session, test_settings)
    await svc.remember_fact(
        memory_user.id,
        subject="lund",
        predicate="stored_in",
        object_summary="Downloads",
    )
    counts = await svc.forget_topic(memory_user.id, "lund")
    assert counts["facts"] >= 1
    remaining = await db_session.execute(
        select(MemoryFact).where(
            MemoryFact.user_id == memory_user.id, MemoryFact.valid_until.is_(None)
        )
    )
    assert all("lund" not in f.subject for f in remaining.scalars().all())


@pytest.mark.asyncio
async def test_memory_overview_api(auth_client: AsyncClient, paired_client_token) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.get("/api/v1/memory/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["local_only"] is True
    assert data["vault_invisible"] is True


@pytest.mark.asyncio
async def test_memory_profile_api(auth_client: AsyncClient, paired_client_token) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post("/api/v1/memory/profile", json={"profile": "broad_local"})
    assert resp.status_code == 200
    assert resp.json()["access_profile"] == "broad_local"


@pytest.mark.asyncio
async def test_chat_memory_status(auth_client: AsyncClient, paired_client_token) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post("/api/v1/chat", json={"message": "memory status"})
    assert resp.status_code == 200
    assert "Local memory status" in resp.json()["response"]


@pytest.mark.asyncio
async def test_vault_folder_api_blocked(
    auth_client: AsyncClient,
    paired_client_token,
    memory_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("nova_core.memory.vault.Path.home", lambda: memory_home)
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    vault_path = str(memory_home / "NOVA_VAULT")
    resp = await auth_client.post("/api/v1/memory/include-folder", json={"path": vault_path})
    assert resp.status_code == 403
    assert "NOVA_VAULT" in resp.json()["detail"] or "inaccessible" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_audit_chain_integrity(
    db_session: AsyncSession, test_settings: Settings, memory_user: User
) -> None:
    svc = MemoryKernelService(db_session, test_settings)
    await svc.set_access_profile(memory_user.id, AccessProfile.MINIMAL)
    assert await svc.audit_integrity(memory_user.id) is True
