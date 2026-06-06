"""Phase 3D provider-aware security model tests."""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.providers.router import ProviderName
from nova_core.tools.protected_paths import PROTECTED_PATH_MESSAGE, is_protected_path
from nova_core.tools.provider_security import (
    FileTransmissionDecision,
    evaluate_file_transmission,
    scrub_runtime_detail,
)
from nova_core.tools.safe_paths import resolve_allowed_path
from nova_core.tools.safe_readonly import SafeReadonlyTools


def test_nova_vault_blocked() -> None:
    path = str(Path.home() / "NOVA_VAULT" / "secret.txt")
    assert is_protected_path(path) is True


def test_ssh_id_rsa_blocked() -> None:
    path = str(Path.home() / ".ssh" / "id_rsa")
    assert is_protected_path(path) is True


def test_repo_env_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "nova"
    project.mkdir()
    secret = project / ".env"
    secret.write_text("SECRET=1", encoding="utf-8")
    monkeypatch.setattr(
        "nova_core.tools.safe_paths.expand_allowed_roots",
        lambda roots=None: [project.resolve()],
    )
    with pytest.raises(Exception):
        resolve_allowed_path(str(secret), allowed_roots=[str(project)])


def test_pem_and_key_blocked() -> None:
    assert is_protected_path("/tmp/test.pem") is True
    assert is_protected_path("/tmp/certificate.key") is True
    assert is_protected_path("/tmp/identity.p12") is True


def test_local_provider_can_read_normal_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "nova"
    project.mkdir()
    readme = project / "README.md"
    readme.write_text("hello nova", encoding="utf-8")
    monkeypatch.setattr(
        "nova_core.tools.safe_paths.expand_allowed_roots",
        lambda roots=None: [project.resolve()],
    )
    tools = SafeReadonlyTools(allowed_roots=[str(project)])
    result = tools.read_file(str(readme))
    assert result.success is True
    assert "hello nova" in result.output["content"]


def test_cloud_provider_cannot_receive_file_without_approval() -> None:
    evaluation = evaluate_file_transmission(
        ProviderName.OPENAI,
        "~/Projects/nova/README.md",
        approved=False,
    )
    assert evaluation.decision == FileTransmissionDecision.BLOCK_CLOUD_APPROVAL


def test_local_provider_allows_non_protected_file() -> None:
    evaluation = evaluate_file_transmission(
        ProviderName.LOCAL,
        "~/Projects/nova/README.md",
        approved=False,
    )
    assert evaluation.decision == FileTransmissionDecision.ALLOW


def test_runtime_detail_scrubs_secrets() -> None:
    assert scrub_runtime_detail("sk-live-abc123") == "redacted"
    assert scrub_runtime_detail("200") == "200"


@pytest.mark.asyncio
async def test_protected_path_block_audit(
    auth_client: AsyncClient, paired_client_token, db_session: AsyncSession
) -> None:
    from nova_core.models.orm import AuditEvent

    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post(
        "/api/v1/chat",
        json={"message": "read file ~/.ssh/id_rsa"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["blocked"] is True
    assert PROTECTED_PATH_MESSAGE in data["response"]

    result = await db_session.execute(
        select(AuditEvent)
        .where(AuditEvent.action == "chat.action_blocked")
        .where(AuditEvent.details["reason"].as_string() == "protected_path_block")
    )
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_runtime_status_does_not_leak_key_values(
    auth_client: AsyncClient, paired_client_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nova_core.providers.runtime import ProviderHealth, ProviderRuntime

    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    async def fake_health(_self):  # type: ignore[no-untyped-def]
        return [
            ProviderHealth(
                provider=ProviderName.LOCAL,
                configured=True,
                paid=False,
                healthy=True,
                mode="ollama",
                detail="200",
            ),
            ProviderHealth(
                provider=ProviderName.OPENAI,
                configured=True,
                paid=True,
                healthy=True,
                mode="configured",
                detail="sk-secret-key-value",
            ),
        ]

    async def fake_fetch(_self, _provider):  # type: ignore[no-untyped-def]
        return ["qwen2.5:7b"]

    async def fake_resolve(_self, _provider):  # type: ignore[no-untyped-def]
        return "qwen2.5:7b"

    monkeypatch.setattr(ProviderRuntime, "health_checks", fake_health)
    monkeypatch.setattr(ProviderRuntime, "_fetch_ollama_models", fake_fetch)
    monkeypatch.setattr(ProviderRuntime, "_resolve_ollama_model", fake_resolve)

    resp = await auth_client.get("/api/v1/runtime/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider_badge"] == "local · qwen2.5:7b"
    paid = next(p for p in body["providers"] if p["provider"] == "openai")
    assert paid["detail"] == "redacted"
    assert "sk-" not in str(body)
