"""Deterministic template Forge engine — existing NOVA app builder."""

from __future__ import annotations

from pathlib import Path

from nova_core.forge.engines.base import (
    ForgeConstraints,
    ForgeEngineResult,
    ForgeTask,
)
from nova_core.forge.execution import write_engine_prompt
from nova_core.forge.project_validation import outcome_to_engine_result, run_project_validation
from nova_core.orchestration.app_builder import build_app, project_path_for_request
from nova_core.orchestration.app_request import parse_app_request


class DeterministicTemplateEngine:
    engine_id = "deterministic_template"
    display_name = "Deterministic Template"

    def available(self) -> bool:
        return True

    def setup_hint(self) -> str:
        return "Built-in NOVA template engine (always available)."

    def capabilities(self) -> list[str]:
        return ["scaffold", "react_vite", "local_preview", "npm_build"]

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
        parsed = parse_app_request(task.request)
        if parsed is None:
            return ForgeEngineResult(
                engine_id=self.engine_id,
                success=False,
                summary="Could not parse app build request.",
                evidence_paths=[str(prompt_path)],
            )
        project = project_path_for_request(parsed)
        try:
            project.resolve().relative_to(constraints.workspace.resolve())
        except ValueError:
            return ForgeEngineResult(
                engine_id=self.engine_id,
                success=False,
                summary="Project path outside workspace.",
                evidence_paths=[str(prompt_path)],
            )
        result = build_app(parsed, run_npm=True, start_preview=True)
        return ForgeEngineResult(
            engine_id=self.engine_id,
            success=result.build_passed,
            summary=f"Template build for {parsed.app_name}",
            evidence_paths=[str(prompt_path), result.project_path],
            files_touched=result.files_written,
            validation_passed=result.build_passed,
        )

    def run_validation(self, workspace: Path, constraints: ForgeConstraints) -> ForgeEngineResult:
        outcome = run_project_validation(workspace, constraints)
        return outcome_to_engine_result(outcome, engine_id=self.engine_id)

    def summarize_result(self, result: ForgeEngineResult) -> str:
        return result.summary

    def evidence_paths(self, result: ForgeEngineResult) -> list[str]:
        return result.evidence_paths
