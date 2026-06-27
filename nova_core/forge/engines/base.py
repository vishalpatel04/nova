"""Forge engine base protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ForgeTask:
    request: str
    app_spec_summary: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    validation_command: str = "npm run build"


@dataclass(frozen=True)
class ForgeConstraints:
    workspace: Path
    allowed_paths: tuple[str, ...] = ("~/Projects/nova-workspace",)
    forbidden_patterns: tuple[str, ...] = (
        "NOVA_VAULT",
        ".env",
        "id_rsa",
        ".pem",
    )
    timeout_seconds: float = 300.0
    allow_git_push: bool = False
    allow_deploy: bool = False


@dataclass
class ForgeEngineResult:
    engine_id: str
    success: bool
    summary: str
    stdout: str = ""
    stderr: str = ""
    evidence_paths: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    validation_passed: bool | None = None
    validation_strategy: str = ""
    validation_status: str = ""
    reason: str = ""
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "success": self.success,
            "summary": self.summary,
            "stdout": self.stdout[:4000],
            "stderr": self.stderr[:4000],
            "evidence_paths": self.evidence_paths,
            "files_touched": self.files_touched[:32],
            "validation_passed": self.validation_passed,
            "validation_strategy": self.validation_strategy,
            "validation_status": self.validation_status,
            "reason": self.reason,
            "fallback_used": self.fallback_used,
        }


class ForgeEngine(Protocol):
    @property
    def engine_id(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    def available(self) -> bool: ...

    def setup_hint(self) -> str: ...

    def capabilities(self) -> list[str]: ...

    def run_task(
        self,
        task: ForgeTask,
        workspace: Path,
        constraints: ForgeConstraints,
    ) -> ForgeEngineResult: ...

    def run_validation(
        self, workspace: Path, constraints: ForgeConstraints
    ) -> ForgeEngineResult: ...

    def summarize_result(self, result: ForgeEngineResult) -> str: ...

    def evidence_paths(self, result: ForgeEngineResult) -> list[str]: ...
