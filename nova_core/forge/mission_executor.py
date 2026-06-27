"""Live Forge execution for Agent OS missions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nova_core.forge.engines.base import ForgeTask
from nova_core.forge.engines.registry import get_engine
from nova_core.forge.execution import default_constraints, write_engine_prompt
from nova_core.orchestration.app_builder import (
    BuildResult,
    build_app,
    clean_project_workspace,
    project_path_for_request,
)
from nova_core.orchestration.app_request import AppRequest, parse_app_request
from nova_core.orchestration.app_spec import build_app_spec
from nova_core.schemas.settings import Settings


@dataclass
class ForgeExecutionResult:
    engine_id: str
    status: str
    workspace_path: str = ""
    files_changed: list[str] = field(default_factory=list)
    commands_run: list[dict[str, Any]] = field(default_factory=list)
    validation_status: str = "unknown"
    preview_url: str | None = None
    preview_log_path: str | None = None
    preview_reachable: bool | None = None
    evidence_paths: list[str] = field(default_factory=list)
    stdout_log: str = ""
    stderr_log: str = ""
    setup_hint: str = ""
    fallback_used: bool = False
    build_passed: bool = False
    app_name: str = ""
    app_type: str = ""
    template_id: str = ""
    runtime: str = "web"
    run_command: str | None = None
    engine_display_name: str = ""
    engine_reason: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "files_changed": self.files_changed[:32],
            "commands_run": self.commands_run,
            "validation_status": self.validation_status,
            "preview_url": self.preview_url,
            "preview_log_path": self.preview_log_path,
            "preview_reachable": self.preview_reachable,
            "evidence_paths": self.evidence_paths,
            "stdout_log": self.stdout_log[:4000],
            "stderr_log": self.stderr_log[:4000],
            "setup_hint": self.setup_hint,
            "fallback_used": self.fallback_used,
            "build_passed": self.build_passed,
            "app_name": self.app_name,
            "app_type": self.app_type,
            "template_id": self.template_id,
            "runtime": self.runtime,
            "run_command": self.run_command,
            "engine_display_name": self.engine_display_name,
            "engine_reason": self.engine_reason,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForgeExecutionResult:
        return cls(
            engine_id=str(data.get("engine_id", "deterministic_template")),
            status=str(data.get("status", "unknown")),
            workspace_path=str(data.get("workspace_path", "")),
            files_changed=list(data.get("files_changed") or []),
            commands_run=list(data.get("commands_run") or []),
            validation_status=str(data.get("validation_status", "unknown")),
            preview_url=data.get("preview_url"),
            preview_log_path=data.get("preview_log_path"),
            preview_reachable=data.get("preview_reachable"),
            evidence_paths=list(data.get("evidence_paths") or []),
            stdout_log=str(data.get("stdout_log", "")),
            stderr_log=str(data.get("stderr_log", "")),
            setup_hint=str(data.get("setup_hint", "")),
            fallback_used=bool(data.get("fallback_used")),
            build_passed=bool(data.get("build_passed")),
            app_name=str(data.get("app_name", "")),
            app_type=str(data.get("app_type", "")),
            template_id=str(data.get("template_id", "")),
            runtime=str(data.get("runtime", "web")),
            run_command=data.get("run_command"),
            engine_display_name=str(data.get("engine_display_name", "")),
            engine_reason=str(data.get("engine_reason", "")),
            summary=str(data.get("summary", "")),
        )


def _build_result_to_forge(
    build: BuildResult,
    *,
    engine_id: str,
    engine_display_name: str,
    fallback_used: bool = False,
    setup_hint: str = "",
    summary: str = "",
) -> ForgeExecutionResult:
    commands: list[dict[str, Any]] = []
    if build.install:
        commands.append(
            {
                "command": build.install.command,
                "exit_code": build.install.exit_code,
                "success": build.install.success,
            }
        )
    if build.build:
        commands.append(
            {
                "command": build.build.command,
                "exit_code": build.build.exit_code,
                "success": build.build.success,
            }
        )
    return ForgeExecutionResult(
        engine_id=engine_id,
        status="success" if build.build_passed else "failed",
        workspace_path=build.project_path,
        files_changed=build.files_written,
        commands_run=commands,
        validation_status="pass" if build.build_passed else "fail",
        preview_url=build.preview_url,
        preview_log_path=build.preview.log_path if build.preview else None,
        preview_reachable=build.preview.reachable if build.preview else None,
        fallback_used=fallback_used,
        build_passed=build.build_passed,
        app_name=build.app_name,
        app_type=build.app_type,
        template_id=build.template_id,
        runtime=build.runtime,
        run_command=build.run_command,
        engine_display_name=engine_display_name,
        summary=summary or f"Template build for {build.app_name}",
        setup_hint=setup_hint,
    )


def _run_deterministic(
    app_request: AppRequest,
    *,
    project_path: Path,
    run_npm: bool,
    start_preview: bool,
    clean_workspace: bool,
    engine_display_name: str,
    fallback_used: bool = False,
    setup_hint: str = "",
    summary: str = "",
) -> ForgeExecutionResult:
    if clean_workspace:
        clean_project_workspace(project_path)
    build = build_app(
        app_request,
        run_npm=run_npm,
        start_preview=start_preview,
        project_path=project_path,
    )
    return _build_result_to_forge(
        build,
        engine_id="deterministic_template",
        engine_display_name=engine_display_name,
        fallback_used=fallback_used,
        setup_hint=setup_hint,
        summary=summary,
    )


def execute_forge_build(
    *,
    user_request: str,
    engine_id: str,
    settings: Settings | None = None,
    run_npm: bool = True,
    start_preview: bool = True,
    clean_workspace: bool = False,
    allow_fallback: bool = False,
    app_request: AppRequest | None = None,
) -> ForgeExecutionResult:
    """Run the selected Forge engine for a live Agent OS mission."""
    cfg = settings or Settings()
    parsed = app_request or parse_app_request(user_request)
    if parsed is None:
        parsed = parse_app_request(f"build a simple web app for {user_request}")
    if parsed is None:
        return ForgeExecutionResult(
            engine_id=engine_id,
            status="failed",
            summary="Could not parse app build request.",
        )

    project_path = project_path_for_request(parsed)
    spec = build_app_spec(parsed)
    engine = get_engine(engine_id, cfg)
    if engine is None:
        engine_id = "deterministic_template"
        engine = get_engine("deterministic_template", cfg)
    assert engine is not None

    if engine_id != "deterministic_template" and not engine.available():
        hint = engine.setup_hint()
        if allow_fallback:
            fallback = get_engine("deterministic_template", cfg)
            assert fallback is not None
            result = _run_deterministic(
                parsed,
                project_path=project_path,
                run_npm=run_npm,
                start_preview=start_preview,
                clean_workspace=clean_workspace,
                engine_display_name=fallback.display_name,
                fallback_used=True,
                setup_hint=hint,
                summary=f"{hint}\n\nFallback: deterministic template scaffold.",
            )
            result.engine_reason = f"Requested {engine.display_name} unavailable"
            return result
        return ForgeExecutionResult(
            engine_id=engine_id,
            status="unavailable",
            engine_display_name=engine.display_name,
            setup_hint=hint,
            summary=f"{engine.display_name} is not configured.",
            engine_reason=f"Requested {engine.display_name}",
        )

    if engine_id == "deterministic_template":
        return _run_deterministic(
            parsed,
            project_path=project_path,
            run_npm=run_npm,
            start_preview=start_preview,
            clean_workspace=clean_workspace,
            engine_display_name=engine.display_name,
            fallback_used=allow_fallback and engine_id == "deterministic_template",
        )

    constraints = default_constraints(project_path)
    evidence_dir = project_path / ".nova-forge-evidence"
    prompt_path = write_engine_prompt(
        evidence_dir,
        engine_id=engine.engine_id,
        task=ForgeTask(
            request=user_request,
            app_spec_summary=spec.description,
            acceptance_criteria=list(spec.acceptance_criteria),
        ),
        constraints=constraints,
    )
    if clean_workspace:
        clean_project_workspace(project_path)

    task = ForgeTask(
        request=user_request,
        app_spec_summary=spec.description,
        acceptance_criteria=list(spec.acceptance_criteria),
    )
    task_result = engine.run_task(task, project_path, constraints)
    validation = engine.run_validation(project_path, constraints)

    commands: list[dict[str, Any]] = []
    if validation.stdout or validation.stderr:
        commands.append({"command": "validation", "success": validation.success})

    build_passed = task_result.success and (validation.validation_passed is not False)
    return ForgeExecutionResult(
        engine_id=engine.engine_id,
        status="success" if build_passed else "failed",
        workspace_path=str(project_path),
        files_changed=task_result.files_touched,
        commands_run=commands,
        validation_status="pass" if validation.validation_passed else "fail",
        evidence_paths=[str(prompt_path), *task_result.evidence_paths],
        stdout_log=task_result.stdout,
        stderr_log=task_result.stderr,
        build_passed=build_passed,
        app_name=parsed.app_name,
        app_type=parsed.app_type,
        template_id=engine.engine_id,
        runtime=parsed.runtime,
        engine_display_name=engine.display_name,
        summary=task_result.summary,
        fallback_used=task_result.fallback_used,
    )
