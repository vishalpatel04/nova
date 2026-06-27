"""Project-aware Forge validation — detect project type before running commands."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from nova_core.forge.engines.base import ForgeConstraints, ForgeEngineResult
from nova_core.forge.execution import run_safe_command

MAX_PYTHON_FILES = 200

_APP_MARKERS = (
    "package.json",
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
)

_README_NAMES = ("README.md", "README.rst", "README.txt", "readme.md")


@dataclass(frozen=True)
class ProjectValidationOutcome:
    validation_strategy: str
    validation_status: str
    validation_passed: bool | None
    success: bool
    summary: str
    reason: str
    stdout: str = ""
    stderr: str = ""
    command: str = ""


def _has_app_markers(root: Path) -> bool:
    return any((root / name).is_file() for name in _APP_MARKERS)


def _is_docs_only(root: Path) -> bool:
    if _has_app_markers(root):
        return False
    has_readme = any((root / name).is_file() for name in _README_NAMES)
    has_docs_dir = (root / "docs").is_dir()
    return has_readme or has_docs_dir


def _read_npm_scripts(package_json: Path) -> dict[str, str]:
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {str(key): str(value) for key, value in scripts.items()}


def _python_marker_present(root: Path) -> bool:
    return any(
        (root / name).is_file() for name in ("pyproject.toml", "setup.py", "requirements.txt")
    )


def _count_python_files(root: Path) -> int:
    count = 0
    for path in root.rglob("*.py"):
        if ".nova-forge-evidence" in path.parts:
            continue
        count += 1
    return count


def _skipped_outcome(
    *,
    strategy: str,
    status: str,
    summary: str,
    reason: str,
) -> ProjectValidationOutcome:
    return ProjectValidationOutcome(
        validation_strategy=strategy,
        validation_status=status,
        validation_passed=True,
        success=True,
        summary=summary,
        reason=reason,
    )


def run_project_validation(
    workspace: Path,
    constraints: ForgeConstraints,
) -> ProjectValidationOutcome:
    root = workspace.resolve()
    if not root.is_dir():
        return _skipped_outcome(
            strategy="skipped_unknown_project_type",
            status="skipped_unknown_project_type",
            summary="Validation skipped: no known build/test command",
            reason="Workspace is not a directory",
        )

    package_json = root / "package.json"
    if package_json.is_file():
        scripts = _read_npm_scripts(package_json)
        if "build" in scripts:
            code, out, err = run_safe_command(
                ["npm", "run", "build"],
                cwd=root,
                constraints=constraints,
            )
            passed = code == 0
            return ProjectValidationOutcome(
                validation_strategy="npm_build",
                validation_status="pass" if passed else "fail",
                validation_passed=passed,
                success=passed,
                summary="npm run build",
                reason="package.json scripts.build",
                stdout=out,
                stderr=err,
                command="npm run build",
            )
        if "test" in scripts:
            code, out, err = run_safe_command(
                ["npm", "test"],
                cwd=root,
                constraints=constraints,
            )
            passed = code == 0
            return ProjectValidationOutcome(
                validation_strategy="npm_test",
                validation_status="pass" if passed else "fail",
                validation_passed=passed,
                success=passed,
                summary="npm test",
                reason="package.json scripts.test (no build script)",
                stdout=out,
                stderr=err,
                command="npm test",
            )
        return _skipped_outcome(
            strategy="skipped_no_npm_scripts",
            status="skipped_no_npm_scripts",
            summary="Validation skipped: no npm build/test scripts",
            reason="package.json present but scripts.build and scripts.test missing",
        )

    if _python_marker_present(root):
        py_count = _count_python_files(root)
        if py_count > MAX_PYTHON_FILES:
            return _skipped_outcome(
                strategy="skipped_python_too_large",
                status="skipped_python_too_large",
                summary="Validation skipped: Python project too large for compileall",
                reason=f"{py_count} Python files exceeds limit of {MAX_PYTHON_FILES}",
            )
        code, out, err = run_safe_command(
            ["python3", "-m", "compileall", "."],
            cwd=root,
            constraints=constraints,
        )
        if code != 0:
            code, out, err = run_safe_command(
                ["python", "-m", "compileall", "."],
                cwd=root,
                constraints=constraints,
            )
        passed = code == 0
        return ProjectValidationOutcome(
            validation_strategy="python_compileall",
            validation_status="pass" if passed else "fail",
            validation_passed=passed,
            success=passed,
            summary="python -m compileall .",
            reason="Python project marker detected",
            stdout=out,
            stderr=err,
            command="python -m compileall .",
        )

    if _is_docs_only(root):
        return _skipped_outcome(
            strategy="skipped_docs_only",
            status="skipped_docs_only",
            summary="Validation skipped: docs-only project",
            reason="README or docs/ present without app build markers",
        )

    return _skipped_outcome(
        strategy="skipped_unknown_project_type",
        status="skipped_unknown_project_type",
        summary="Validation skipped: no known build/test command",
        reason="No package.json, Python markers, or docs-only pattern detected",
    )


def outcome_to_engine_result(
    outcome: ProjectValidationOutcome,
    *,
    engine_id: str,
) -> ForgeEngineResult:
    return ForgeEngineResult(
        engine_id=engine_id,
        success=outcome.success,
        summary=outcome.summary,
        stdout=outcome.stdout,
        stderr=outcome.stderr,
        validation_passed=outcome.validation_passed,
        validation_strategy=outcome.validation_strategy,
        validation_status=outcome.validation_status,
        reason=outcome.reason,
    )
