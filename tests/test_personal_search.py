"""Tests for read-only personal-folder search scopes."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.projects import ProjectService
from nova_core.auth.principal import Principal
from nova_core.tools.personal_search import PersonalSearchTool, format_search_results
from nova_core.tools.protected_paths import PROTECTED_PATH_MESSAGE
from nova_core.tools.search_scopes import (
    is_probably_binary,
    resolve_search_scope,
    should_skip_file,
)


@pytest.fixture
def personal_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    for name in ("Projects", "Desktop", "Documents", "Downloads"):
        (home / name).mkdir(parents=True)
    (home / "Downloads" / "notes.txt").write_text("lund university notes", encoding="utf-8")
    (home / "Documents" / "report.txt").write_text("annual lund report", encoding="utf-8")
    (home / "Desktop" / "todo.txt").write_text("visit lund", encoding="utf-8")
    (home / "Projects" / "nova" / "README.md").parent.mkdir(parents=True)
    (home / "Projects" / "nova" / "README.md").write_text("nova lund", encoding="utf-8")
    (home / "Downloads" / ".env").write_text("SECRET=1", encoding="utf-8")
    (home / "Downloads" / "binary.bin").write_bytes(b"\x00\x01\x02")
    (home / "Library").mkdir()
    (home / "Library" / "secret.txt").write_text("lund hidden", encoding="utf-8")
    return home


@pytest.fixture
def search_roots(personal_home: Path) -> list[str]:
    return [str(personal_home / name) for name in ("Projects", "Desktop", "Documents", "Downloads")]


@pytest.fixture
def allow_demo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "demo-proj"
    root.mkdir()
    (root / "README.md").write_text("# Demo", encoding="utf-8")

    def _fake_roots(roots: list[str] | None = None) -> list[Path]:
        return [root.resolve()]

    monkeypatch.setattr("nova_core.tools.safe_paths.expand_allowed_roots", _fake_roots)
    monkeypatch.setattr("nova_core.project.context.expand_allowed_roots", _fake_roots)
    return root.resolve()


def test_search_downloads_allowed_read_only(search_roots: list[str]) -> None:
    tool = PersonalSearchTool(search_roots=search_roots)
    result = tool.search_scope("lund", str(Path(search_roots[3])))
    assert result.success
    assert result.output is not None
    assert result.output["match_count"] >= 1


def test_search_documents_allowed_read_only(search_roots: list[str]) -> None:
    tool = PersonalSearchTool(search_roots=search_roots)
    result = tool.search_scope("lund", str(Path(search_roots[2])))
    assert result.success
    assert result.output is not None
    assert result.output["match_count"] >= 1


def test_search_desktop_allowed_read_only(search_roots: list[str]) -> None:
    tool = PersonalSearchTool(search_roots=search_roots)
    result = tool.search_scope("lund", str(Path(search_roots[1])))
    assert result.success


def test_search_projects_allowed_read_only(search_roots: list[str]) -> None:
    tool = PersonalSearchTool(search_roots=search_roots)
    result = tool.search_scope("lund", str(Path(search_roots[0])))
    assert result.success


def test_all_approved_roots_search_bounded(search_roots: list[str]) -> None:
    tool = PersonalSearchTool(search_roots=search_roots)
    result = tool.search_all_approved("lund")
    assert result.success
    assert result.output is not None
    assert result.output["match_count"] >= 3
    formatted = format_search_results("lund", result.output)
    assert "Found" in formatted


def test_nova_vault_blocked(personal_home: Path, search_roots: list[str]) -> None:
    vault = personal_home / "NOVA_VAULT"
    vault.mkdir()
    (vault / "secret.txt").write_text("lund", encoding="utf-8")
    validation = resolve_search_scope(str(vault), search_roots=search_roots)
    assert not validation.allowed
    assert validation.reason == PROTECTED_PATH_MESSAGE


def test_ssh_blocked(personal_home: Path, search_roots: list[str]) -> None:
    ssh = personal_home / ".ssh"
    ssh.mkdir()
    validation = resolve_search_scope(str(ssh), search_roots=search_roots)
    assert not validation.allowed


def test_library_blocked(personal_home: Path, search_roots: list[str]) -> None:
    validation = resolve_search_scope(str(personal_home / "Library"), search_roots=search_roots)
    assert not validation.allowed


def test_env_skipped(search_roots: list[str]) -> None:
    env_path = Path(search_roots[3]) / ".env"
    assert should_skip_file(env_path)


def test_binary_skipped(search_roots: list[str]) -> None:
    binary = Path(search_roots[3]) / "binary.bin"
    assert is_probably_binary(binary)


def test_symlink_escape_blocked(
    personal_home: Path, search_roots: list[str], tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("lund", encoding="utf-8")
    link = personal_home / "Downloads" / "escape-link"
    link.symlink_to(outside)
    validation = resolve_search_scope(str(link), search_roots=search_roots)
    assert not validation.allowed


@pytest.mark.asyncio
async def test_stale_deleted_project_cleared(
    db_session: AsyncSession,
    test_settings,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    device_id, _ = paired_client_token
    principal = Principal(
        principal_type="device",
        principal_id=device_id,
        user_id="arth",
        device_id=device_id,
    )
    svc = ProjectService(db_session, test_settings)
    record = await svc.set_active_project(principal, str(allow_demo_root))
    assert record.project_name == allow_demo_root.name
    import shutil

    shutil.rmtree(allow_demo_root)
    cleared = await svc.get_active_project_or_none(principal)
    assert cleared is None


@pytest.mark.asyncio
async def test_chat_search_downloads(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    personal_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots = [
        str(personal_home / name) for name in ("Projects", "Desktop", "Documents", "Downloads")
    ]

    def _fake_search_roots(configured: list[str] | None = None) -> list[Path]:
        del configured
        return [Path(r).resolve() for r in roots]

    monkeypatch.setenv("HOME", str(personal_home))
    monkeypatch.setattr("nova_core.tools.search_scopes.expand_search_roots", _fake_search_roots)
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post(
        "/api/v1/chat",
        json={"message": f"search lund in {personal_home / 'Downloads'}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["response"]
    assert "Blocked" not in body or "Found" in body
    assert "Found" in body or "0 matches" in body


@pytest.mark.asyncio
async def test_chat_set_project_returns_active_project(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post(
        "/api/v1/chat",
        json={"message": f"set project {allow_demo_root}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("active_project") == allow_demo_root.name


@pytest.mark.asyncio
async def test_chat_search_computer_prompt(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post(
        "/api/v1/chat",
        json={"message": "search my computer for lund"},
    )
    assert resp.status_code == 200
    assert resp.json()["intent"] == "archive_search"
    assert "File Explorer" not in resp.json()["response"]


def test_demo_helpers_restore_present() -> None:
    text = Path("scripts/demo_project_helpers.sh").read_text(encoding="utf-8")
    assert "demo_save_active_project" in text
    assert "demo_restore_active_project" in text
