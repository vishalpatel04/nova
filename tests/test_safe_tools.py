"""Safe read-only tool tests."""

from pathlib import Path

import pytest

from nova_core.tools.policy import BLOCKED_MESSAGE, ToolDecision, ToolPolicy
from nova_core.tools.safe_paths import is_blocked_name, resolve_allowed_path
from nova_core.tools.safe_readonly import SafeReadonlyTools


def test_allowlisted_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "nova"
    project.mkdir()
    (project / "README.md").write_text("hello", encoding="utf-8")
    monkeypatch.setattr(
        "nova_core.tools.safe_paths.expand_allowed_roots",
        lambda roots=None: [project.resolve()],
    )
    tools = SafeReadonlyTools(allowed_roots=[str(project)])
    result = tools.list_directory(str(project))
    assert result.success is True
    assert any(entry["name"] == "README.md" for entry in result.output["entries"])


def test_secret_path_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "nova"
    project.mkdir()
    secret = project / ".env"
    secret.write_text("SECRET=1", encoding="utf-8")
    monkeypatch.setattr(
        "nova_core.tools.safe_paths.expand_allowed_roots",
        lambda roots=None: [project.resolve()],
    )
    with pytest.raises(PermissionError):
        resolve_allowed_path(str(secret), allowed_roots=[str(project)])


def test_env_filename_blocked() -> None:
    assert is_blocked_name(".env") is True
    assert is_blocked_name("id_rsa") is True


def test_read_file_within_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "nova"
    project.mkdir()
    file_path = project / "notes.txt"
    file_path.write_text("safe content", encoding="utf-8")
    monkeypatch.setattr(
        "nova_core.tools.safe_paths.expand_allowed_roots",
        lambda roots=None: [project.resolve()],
    )
    tools = SafeReadonlyTools(allowed_roots=[str(project)])
    result = tools.read_file(str(file_path))
    assert result.success is True
    assert "safe content" in result.output["content"]


def test_policy_blocks_shell_category() -> None:
    policy = ToolPolicy({"approval": {"required_categories": ["shell"]}})
    evaluation = policy.evaluate("shell", category="shell")
    assert evaluation.decision == ToolDecision.BLOCK
    assert evaluation.reason == BLOCKED_MESSAGE


def test_policy_auto_approves_readonly_tools() -> None:
    policy = ToolPolicy({"approval": {"auto_approve_categories": ["filesystem_read"]}})
    evaluation = policy.evaluate("read_file", category="filesystem_read")
    assert evaluation.decision == ToolDecision.AUTO_APPROVE
