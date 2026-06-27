"""Tests for project-aware Forge validation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from nova_core.forge.engines.base import ForgeConstraints
from nova_core.forge.engines.deterministic_template import DeterministicTemplateEngine
from nova_core.forge.project_validation import run_project_validation


@pytest.fixture
def constraints(tmp_path: Path) -> ForgeConstraints:
    return ForgeConstraints(workspace=tmp_path)


def test_readme_only_project_skips_validation_successfully(
    tmp_path: Path, constraints: ForgeConstraints
) -> None:
    root = tmp_path / "codex-test"
    root.mkdir()
    (root / "README.md").write_text("# Codex test\n", encoding="utf-8")
    outcome = run_project_validation(root, constraints)
    assert outcome.validation_status == "skipped_docs_only"
    assert outcome.validation_strategy == "skipped_docs_only"
    assert outcome.success is True
    assert outcome.validation_passed is True
    assert outcome.summary == "Validation skipped: docs-only project"
    assert "ENOENT" not in outcome.stderr


def test_package_json_with_build_runs_npm_build(
    tmp_path: Path, constraints: ForgeConstraints
) -> None:
    root = tmp_path / "web-app"
    root.mkdir()
    (root / "package.json").write_text(
        json.dumps({"scripts": {"build": "echo build-ok"}}),
        encoding="utf-8",
    )
    with patch("nova_core.forge.project_validation.run_safe_command", return_value=(0, "ok", "")):
        outcome = run_project_validation(root, constraints)
    assert outcome.validation_strategy == "npm_build"
    assert outcome.validation_status == "pass"
    assert outcome.validation_passed is True


def test_package_json_with_only_test_runs_npm_test(
    tmp_path: Path, constraints: ForgeConstraints
) -> None:
    root = tmp_path / "web-app"
    root.mkdir()
    (root / "package.json").write_text(
        json.dumps({"scripts": {"test": "echo test-ok"}}),
        encoding="utf-8",
    )
    with patch("nova_core.forge.project_validation.run_safe_command", return_value=(0, "ok", "")):
        outcome = run_project_validation(root, constraints)
    assert outcome.validation_strategy == "npm_test"
    assert outcome.validation_status == "pass"
    assert outcome.command == "npm test"


def test_package_json_no_scripts_skips(tmp_path: Path, constraints: ForgeConstraints) -> None:
    root = tmp_path / "web-app"
    root.mkdir()
    (root / "package.json").write_text(json.dumps({"name": "demo"}), encoding="utf-8")
    outcome = run_project_validation(root, constraints)
    assert outcome.validation_status == "skipped_no_npm_scripts"
    assert outcome.validation_passed is True
    assert outcome.success is True


def test_python_project_runs_compileall(tmp_path: Path, constraints: ForgeConstraints) -> None:
    root = tmp_path / "py-app"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    with patch("nova_core.forge.project_validation.run_safe_command", return_value=(0, "ok", "")):
        outcome = run_project_validation(root, constraints)
    assert outcome.validation_strategy == "python_compileall"
    assert outcome.validation_status == "pass"


def test_unknown_project_skips_without_failure(
    tmp_path: Path, constraints: ForgeConstraints
) -> None:
    root = tmp_path / "misc"
    root.mkdir()
    (root / "notes.txt").write_text("hello", encoding="utf-8")
    outcome = run_project_validation(root, constraints)
    assert outcome.validation_status == "skipped_unknown_project_type"
    assert outcome.validation_passed is True
    assert outcome.success is True


def test_deterministic_engine_validation_docs_only(
    tmp_path: Path, constraints: ForgeConstraints
) -> None:
    root = tmp_path / "docs-only"
    root.mkdir()
    (root / "README.md").write_text("# Docs", encoding="utf-8")
    engine = DeterministicTemplateEngine()
    result = engine.run_validation(root, constraints)
    assert result.validation_status == "skipped_docs_only"
    assert result.validation_passed is True
    assert "ENOENT" not in result.stderr
