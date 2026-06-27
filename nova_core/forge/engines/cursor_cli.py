"""Cursor CLI / cursor-agent Forge adapter."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from nova_core.forge.engines.base import ForgeConstraints, ForgeEngineResult, ForgeTask
from nova_core.forge.engines.deterministic_template import DeterministicTemplateEngine
from nova_core.forge.execution import run_safe_command, write_engine_prompt
from nova_core.schemas.settings import Settings


class CursorCliEngine:
    engine_id = "cursor_cli"
    display_name = "Cursor CLI"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def _candidates(self) -> list[str]:
        rows: list[str] = []
        env_cmd = os.environ.get("NOVA_CURSOR_CMD", "") or getattr(
            self.settings, "nova_cursor_cmd", ""
        )
        if env_cmd:
            rows.append(env_cmd)
        for name in ("cursor-agent", "cursor"):
            path = shutil.which(name)
            if path:
                rows.append(path)
        local_agent = Path.home() / ".local" / "bin" / "cursor-agent"
        if local_agent.is_file():
            rows.append(str(local_agent))
        return rows

    def available(self) -> bool:
        return bool(self._candidates())

    def setup_hint(self) -> str:
        return (
            "Cursor CLI not found.\n"
            "Install Cursor agent CLI or set NOVA_CURSOR_CMD,\n"
            "e.g. export NOVA_CURSOR_CMD='cursor-agent'\n"
            "Checked: cursor-agent, cursor, ~/.local/bin/cursor-agent"
        )

    def capabilities(self) -> list[str]:
        return ["coding_agent", "ide_agent", "multi_file"]

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
        cmd_path = self._candidates()[0] if self._candidates() else ""
        if not cmd_path:
            return ForgeEngineResult(
                engine_id=self.engine_id,
                success=False,
                summary=self.setup_hint(),
                evidence_paths=[str(prompt_path)],
                fallback_used=True,
            )
        cmd = cmd_path.split() + [task.request]
        code, out, err = run_safe_command(cmd, cwd=workspace, constraints=constraints)
        return ForgeEngineResult(
            engine_id=self.engine_id,
            success=code == 0,
            summary="Cursor CLI completed" if code == 0 else "Cursor CLI failed",
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
