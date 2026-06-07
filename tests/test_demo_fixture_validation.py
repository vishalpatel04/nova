"""Demo fixture validation and git branch metadata tests."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from nova_core.project.inspect import inspect_repo, normalize_git_branch
from nova_core.project.validation import pick_validation_command, run_validation_command

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_useful_agent.sh"


def _create_demo_fixture(root: Path, *, with_git: bool = True) -> None:
    """Mirror scripts/demo_useful_agent.sh project layout (stdlib unittest only)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text(
        ".PHONY: test\n\ntest:\n\tpython3 -m unittest discover -s tests -p 'test_*.py' -v\n",
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_demo.py").write_text(
        "import unittest\n\n\n"
        "class DemoTest(unittest.TestCase):\n"
        "    def test_demo(self):\n"
        "        assert False\n",
        encoding="utf-8",
    )
    if not with_git:
        return
    init = subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    if init.returncode != 0:
        pytest.skip("git init unavailable in test environment")
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=demo@nova.local",
            "-c",
            "user.name=NOVA Demo",
            "add",
            "Makefile",
            "tests/test_demo.py",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=demo@nova.local",
            "-c",
            "user.name=NOVA Demo",
            "commit",
            "-q",
            "-m",
            "demo",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )


def test_demo_script_uses_unittest_not_pytest() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "pytest" not in text
    assert "unittest discover" in text
    assert "tests/test_demo.py" in text


def test_normalize_git_branch_rejects_fatal_stderr() -> None:
    root = Path("/tmp/not-used")
    assert normalize_git_branch(root, "fatal: not a git repository") is None
    assert normalize_git_branch(root, "") is None


def test_normalize_git_branch_uninitialized_when_no_commits(tmp_path: Path) -> None:
    root = tmp_path / "empty-git"
    root.mkdir()
    init = subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    if init.returncode != 0:
        pytest.skip("git init unavailable in test environment")
    assert normalize_git_branch(root, "") == "uninitialized"


@pytest.mark.asyncio
async def test_inspect_repo_branch_never_contains_fatal_stderr(tmp_path: Path) -> None:
    root = tmp_path / "no-git"
    root.mkdir()
    (root / "Makefile").write_text("test:\n\ttrue\n", encoding="utf-8")
    inspection = await inspect_repo(root)
    assert "fatal:" not in (inspection.current_branch or "").lower()
    assert inspection.current_branch == ""


@pytest.mark.asyncio
async def test_inspect_repo_with_git_has_branch_name(tmp_path: Path) -> None:
    root = tmp_path / "with-git"
    _create_demo_fixture(root)
    inspection = await inspect_repo(root)
    assert inspection.current_branch
    assert "fatal:" not in inspection.current_branch.lower()
    assert inspection.current_branch in {"main", "master"}


def test_demo_fixture_validation_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "demo-fixture"
    _create_demo_fixture(root, with_git=False)
    monkeypatch.setattr(
        "nova_core.tools.safe_paths.expand_allowed_roots",
        lambda roots=None: [root.resolve()],
    )
    monkeypatch.setattr(
        "nova_core.project.context.expand_allowed_roots",
        lambda roots=None: [root.resolve()],
    )

    cmd = pick_validation_command(root) or "make test"
    assert "pytest" not in cmd

    first = asyncio.run(run_validation_command(root, cmd, allowed_roots=[str(root)]))
    assert first.exit_code != 0
    assert "No module named pytest" not in f"{first.stdout_excerpt}\n{first.stderr_excerpt}"

    target = root / "tests" / "test_demo.py"
    patched = target.read_text(encoding="utf-8").replace("assert False", "assert True", 1)
    target.write_text(patched, encoding="utf-8")

    second = asyncio.run(run_validation_command(root, cmd, allowed_roots=[str(root)]))
    assert second.exit_code == 0, second.stderr_excerpt
