"""Claude Code CLI Forge adapter."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from nova_core.forge.engines.base import ForgeConstraints, ForgeEngineResult, ForgeTask
from nova_core.forge.engines.deterministic_template import DeterministicTemplateEngine
from nova_core.forge.execution import run_safe_command, write_engine_prompt
from nova_core.schemas.settings import Settings


class ClaudeCodeEngine:
    engine_id = "claude_code_cli"
    display_name = "Claude Code CLI"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def _cmd(self) -> str:
        return os.environ.get("NOVA_CLAUDE_CODE_CMD", "") or getattr(
            self.settings, "nova_claude_code_cmd", "claude"
        )

    def available(self) -> bool:
        return bool(shutil.which(self._cmd()))

    def setup_hint(self) -> str:
        return (
            "Claude Code CLI not found.\n"
            "Install Anthropic Claude Code and ensure `claude` is on PATH,\n"
            "or set NOVA_CLAUDE_CODE_CMD.\n"
            "NOVA falls back to deterministic_template."
        )

    def capabilities(self) -> list[str]:
        return ["coding_agent", "refactor", "multi_file"]

    def run_task(
        self,
        task: ForgeTask,
        workspace: Path,
        constraints: ForgeConstraints,
    ) -> ForgeEngineResult:
        evidence_dir = workspace / ".nova-forge-evidence"
        prompt_path = write_engine_prompt(
            evidence_dir, engine_id=self.engine_id, task=task, constraints=constraints
        )
        if not self.available():
            return ForgeEngineResult(
                engine_id=self.engine_id,
                success=False,
                summary=self.setup_hint(),
                evidence_paths=[str(prompt_path)],
                fallback_used=True,
            )
        cmd = [self._cmd(), "-p", task.request]
        code, out, err = run_safe_command(cmd, cwd=workspace, constraints=constraints)
        return ForgeEngineResult(
            engine_id=self.engine_id,
            success=code == 0,
            summary="Claude Code completed" if code == 0 else "Claude Code failed",
            stdout=out,
            stderr=err,
            evidence_paths=[str(prompt_path)],
        )

    def run_validation(self, workspace: Path, constraints: ForgeConstraints) -> ForgeEngineResult:
        return DeterministicTemplateEngine().run_validation(workspace, constraints)

    def summarize_result(self, result: ForgeEngineResult) -> str:
        return result.summary

    def evidence_paths(self, result: ForgeEngineResult) -> list[str]:
        return result.evidence_paths
