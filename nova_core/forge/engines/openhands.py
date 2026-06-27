"""OpenHands Forge adapter — API or subprocess, never auto-install."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import httpx

from nova_core.forge.engines.base import ForgeConstraints, ForgeEngineResult, ForgeTask
from nova_core.forge.execution import run_safe_command, write_engine_prompt
from nova_core.schemas.settings import Settings


class OpenHandsEngine:
    engine_id = "openhands"
    display_name = "OpenHands"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def _url(self) -> str:
        return (
            os.environ.get("NOVA_OPENHANDS_URL", "")
            or getattr(self.settings, "nova_openhands_url", "")
        ).rstrip("/")

    def _cmd(self) -> str:
        return os.environ.get("NOVA_OPENHANDS_CMD", "") or getattr(
            self.settings, "nova_openhands_cmd", ""
        )

    def available(self) -> bool:
        if self._url():
            return True
        if self._cmd():
            return shutil.which(self._cmd().split()[0]) is not None
        return False

    def setup_hint(self) -> str:
        return (
            "OpenHands not configured.\n"
            "Clone external/openhands locally (gitignored) and either:\n"
            "  export NOVA_OPENHANDS_URL=http://127.0.0.1:3000\n"
            "  export NOVA_OPENHANDS_CMD='openhands-cli run'\n"
            "See docs/OPENHANDS_INTEGRATION.md\n"
            "NOVA will fall back to deterministic_template."
        )

    def capabilities(self) -> list[str]:
        return ["coding_agent", "multi_file_edit", "validation"]

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
        if self._url():
            return self._run_via_api(task, workspace, prompt_path)
        return self._run_via_cmd(task, workspace, constraints, prompt_path)

    def _run_via_api(
        self, task: ForgeTask, workspace: Path, prompt_path: Path
    ) -> ForgeEngineResult:
        url = f"{self._url()}/api/tasks"
        payload = {"task": task.request, "workspace": str(workspace)}
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            return ForgeEngineResult(
                engine_id=self.engine_id,
                success=True,
                summary=str(data.get("summary", "OpenHands task submitted")),
                stdout=json.dumps(data)[:4000],
                evidence_paths=[str(prompt_path)],
            )
        except Exception as exc:
            return ForgeEngineResult(
                engine_id=self.engine_id,
                success=False,
                summary=f"OpenHands API error: {exc.__class__.__name__}",
                stderr=str(exc)[:500],
                evidence_paths=[str(prompt_path)],
            )

    def _run_via_cmd(
        self,
        task: ForgeTask,
        workspace: Path,
        constraints: ForgeConstraints,
        prompt_path: Path,
    ) -> ForgeEngineResult:
        cmd = self._cmd().split()
        cmd.extend(["--workspace", str(workspace), "--task", task.request])
        code, out, err = run_safe_command(cmd, cwd=workspace, constraints=constraints)
        return ForgeEngineResult(
            engine_id=self.engine_id,
            success=code == 0,
            summary="OpenHands command completed" if code == 0 else "OpenHands command failed",
            stdout=out,
            stderr=err,
            evidence_paths=[str(prompt_path)],
        )

    def run_validation(self, workspace: Path, constraints: ForgeConstraints) -> ForgeEngineResult:
        from nova_core.forge.engines.deterministic_template import DeterministicTemplateEngine

        return DeterministicTemplateEngine().run_validation(workspace, constraints)

    def summarize_result(self, result: ForgeEngineResult) -> str:
        return result.summary

    def evidence_paths(self, result: ForgeEngineResult) -> list[str]:
        return result.evidence_paths


# noqa: E402 — late import avoided above for circular dependency
