"""Deterministic app builder for NOVA Agent OS missions."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from nova_core.agent_os.workspace import assert_workspace_write, workspace_root
from nova_core.orchestration.app_request import AppRequest, project_dir_name
from nova_core.orchestration.app_spec import AppSpec, build_app_spec
from nova_core.orchestration.preview import PreviewSession, launch_preview, stop_preview
from nova_core.orchestration.templates import _calculator_files as _calc_builder
from nova_core.orchestration.templates import template_for_spec

CALCULATOR_FILES = _calc_builder(
    AppSpec(
        title="NOVA Calculator",
        description="Calculator",
        stack="Vite + React + TypeScript",
        pages=("home",),
        components=("Calculator",),
        user_interactions=("tap",),
        acceptance_criteria=("build passes",),
        template_id="calculator_react_vite",
        app_type="calculator",
        app_name="NOVA Calculator",
    )
)


@dataclass
class CommandResult:
    command: str
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    success: bool


@dataclass
class BuildResult:
    project_path: str
    files_written: list[str]
    install: CommandResult | None
    build: CommandResult | None
    preview: PreviewSession | None
    preview_url: str | None
    build_passed: bool
    app_type: str
    app_name: str
    template_id: str
    runtime: str = "web"
    run_command: str | None = None


@dataclass
class AppMissionResult:
    mission_id: str
    app_name: str
    app_type: str
    path: str
    build_status: str
    preview_url: str | None
    deploy_status: str
    evidence_log: str
    preview_pid: int | None = None
    preview_port: int | None = None
    preview_log_path: str | None = None


def project_path_for_request(request: AppRequest, base: Path | None = None) -> Path:
    root = base or workspace_root()
    return assert_workspace_write(root / project_dir_name(request))


def write_app_files(spec: AppSpec, project_path: Path) -> list[str]:
    root = assert_workspace_write(project_path)
    root.mkdir(parents=True, exist_ok=True)
    template = template_for_spec(spec)
    files = template.build_files(spec)
    written: list[str] = []
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
    return written


def write_calculator_files(project_path: Path | None = None) -> list[str]:
    request = AppRequest(
        raw_user_request="build a calculator app",
        app_type="calculator",
        app_name="NOVA Calculator",
        features=("arithmetic",),
        style_preference="modern",
        deployment_requested=False,
        requires_clarification=False,
    )
    spec = build_app_spec(request)
    return write_app_files(spec, project_path or project_path_for_request(request))


def clean_project_workspace(project_path: Path) -> None:
    if project_path.exists():
        preview_log = project_path / ".nova-preview"
        if preview_log.exists():
            shutil.rmtree(preview_log, ignore_errors=True)
        shutil.rmtree(project_path)


def clean_calculator_workspace(project_path: Path | None = None) -> None:
    request = AppRequest(
        raw_user_request="build a calculator app",
        app_type="calculator",
        app_name="NOVA Calculator",
        features=(),
        style_preference="modern",
        deployment_requested=False,
        requires_clarification=False,
    )
    clean_project_workspace(project_path or project_path_for_request(request))


def run_workspace_command(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 300,
) -> CommandResult:
    assert_workspace_write(cwd)
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(
        command=" ".join(command),
        cwd=str(cwd),
        exit_code=proc.returncode,
        stdout=proc.stdout[-4000:],
        stderr=proc.stderr[-2000:],
        success=proc.returncode == 0,
    )


def build_app(
    request: AppRequest,
    *,
    run_npm: bool = True,
    start_preview: bool = True,
    project_path: Path | None = None,
) -> BuildResult:
    if request.runtime == "cli":
        return build_cli_app(request, project_path=project_path)

    spec = build_app_spec(request)
    root = project_path or project_path_for_request(request)
    files = write_app_files(spec, root)
    install_result: CommandResult | None = None
    build_result: CommandResult | None = None
    preview_session: PreviewSession | None = None
    preview_url: str | None = None

    if run_npm:
        install_result = run_workspace_command(["npm", "install"], cwd=root)
        if install_result.success:
            build_result = run_workspace_command(["npm", "run", "build"], cwd=root)

    build_passed = bool(build_result and build_result.success)

    if build_passed and start_preview:
        preview_session = launch_preview(root)
        if preview_session.reachable:
            preview_url = preview_session.url

    return BuildResult(
        project_path=str(root),
        files_written=files,
        install=install_result,
        build=build_result,
        preview=preview_session,
        preview_url=preview_url,
        build_passed=build_passed,
        app_type=request.app_type,
        app_name=request.app_name,
        template_id=spec.template_id,
        runtime="web",
    )


def build_cli_app(
    request: AppRequest,
    *,
    project_path: Path | None = None,
) -> BuildResult:
    spec = build_app_spec(request)
    root = project_path or project_path_for_request(request)
    files = write_app_files(spec, root)
    syntax_result = run_workspace_command(
        ["python3", "-m", "py_compile", "calculator.py"],
        cwd=root,
    )
    smoke_result: CommandResult | None = None
    if syntax_result.success:
        smoke_result = run_workspace_command(
            ["python3", "calculator.py", "--smoke"],
            cwd=root,
        )
    build_passed = bool(syntax_result.success and smoke_result and smoke_result.success)
    run_command = f"python3 {root / 'calculator.py'}"
    return BuildResult(
        project_path=str(root),
        files_written=files,
        install=syntax_result,
        build=smoke_result,
        preview=None,
        preview_url=None,
        build_passed=build_passed,
        app_type=request.app_type,
        app_name=request.app_name,
        template_id=spec.template_id,
        runtime="cli",
        run_command=run_command,
    )


def build_calculator_app(
    *,
    run_npm: bool = True,
    project_path: Path | None = None,
    start_preview: bool = False,
) -> BuildResult:
    request = AppRequest(
        raw_user_request="build a calculator app",
        app_type="calculator",
        app_name="NOVA Calculator",
        features=("arithmetic", "clear", "decimal", "divide-by-zero", "keyboard"),
        style_preference="modern",
        deployment_requested=False,
        requires_clarification=False,
    )
    return build_app(
        request,
        run_npm=run_npm,
        start_preview=start_preview,
        project_path=project_path,
    )


def expected_calculator_files(project_path: Path | None = None) -> list[Path]:
    request = AppRequest(
        raw_user_request="build a calculator app",
        app_type="calculator",
        app_name="NOVA Calculator",
        features=(),
        style_preference="modern",
        deployment_requested=False,
        requires_clarification=False,
    )
    root = project_path or project_path_for_request(request)
    return [root / rel for rel in CALCULATOR_FILES]


def stop_app_preview(preview_pid: int | None) -> bool:
    if preview_pid is None:
        return False
    return stop_preview(preview_pid)
