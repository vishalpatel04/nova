"""Active project API routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.coding_tasks import CodingTaskService
from apps.api.services.projects import ProjectService
from nova_core.auth.principal import Principal
from nova_core.models.orm import ActiveProject
from nova_core.project.inspect import format_inspection, inspect_repo
from nova_core.project.validation import pick_validation_command, run_validation_command
from nova_core.schemas.api import (
    ActiveProjectResponse,
    CodingTaskResponse,
    RunValidationResponse,
    SetActiveProjectRequest,
)
from nova_core.schemas.settings import get_settings

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_response(record: ActiveProject) -> ActiveProjectResponse:
    return ActiveProjectResponse(
        project_root=record.project_root,
        project_name=record.project_name,
        current_branch=record.current_branch,
        detected_tooling=record.detected_tooling or {},
        last_opened_at=record.last_opened_at,
        user_id=record.user_id,
        device_id=record.device_id,
    )


@router.post("/active", response_model=ActiveProjectResponse)
async def set_active_project(
    body: SetActiveProjectRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ActiveProjectResponse:
    settings = get_settings()
    svc = ProjectService(session, settings)
    record = await svc.set_active_project(principal, body.project_root)
    await session.commit()
    return _project_response(record)


@router.get("/active", response_model=ActiveProjectResponse)
async def get_active_project(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ActiveProjectResponse:
    settings = get_settings()
    svc = ProjectService(session, settings)
    record = await svc.get_active_project(principal)
    return _project_response(record)


@router.post("/inspect")
async def inspect_active_project(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    settings = get_settings()
    svc = ProjectService(session, settings)
    record = await svc.get_active_project(principal)
    from pathlib import Path

    inspection = await inspect_repo(Path(record.project_root))
    record.current_branch = inspection.current_branch
    await session.commit()
    return {
        "project": _project_response(record).model_dump(),
        "inspection": format_inspection(inspection),
    }


@router.post("/validate", response_model=RunValidationResponse)
async def run_project_validation(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> RunValidationResponse:
    from pathlib import Path

    settings = get_settings()
    project_svc = ProjectService(session, settings)
    record = await project_svc.get_active_project(principal)
    root = Path(record.project_root)
    policies = settings.load_yaml("policies.yaml")
    safe_cfg = policies.get("safe_filesystem", {})
    allowed_roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None
    cmd = pick_validation_command(root) or "make test"
    result = await run_validation_command(root, cmd, allowed_roots=allowed_roots)
    await project_svc.upsert_memory(
        principal,
        record.project_root,
        last_validation_command=cmd,
        last_validation_result={
            "exit_code": result.exit_code,
            "stdout": result.stdout_excerpt[:2000],
            "stderr": result.stderr_excerpt[:2000],
        },
    )
    await session.commit()
    return RunValidationResponse(
        command=cmd,
        exit_code=result.exit_code,
        stdout_excerpt=result.stdout_excerpt,
        stderr_excerpt=result.stderr_excerpt,
        blocked=result.blocked,
        block_reason=result.block_reason,
    )


@router.post("/coding-tasks", response_model=CodingTaskResponse)
async def start_coding_task(
    body: Annotated[dict[str, Any], Body()],
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> CodingTaskResponse:
    settings = get_settings()
    svc = CodingTaskService(session, settings)
    request_text = str(body.get("request", "")).strip()
    if not request_text:
        from nova_core.schemas.errors import ValidationError

        raise ValidationError("request is required")
    result = await svc.run_workflow(principal, request_text)
    await session.commit()
    return CodingTaskResponse(
        **{k: v for k, v in result.items() if k in CodingTaskResponse.model_fields}
    )


@router.get("/coding-tasks/{task_id}", response_model=CodingTaskResponse)
async def get_coding_task(
    task_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> CodingTaskResponse:
    settings = get_settings()
    svc = CodingTaskService(session, settings)
    task = await svc.get_task(principal, task_id)
    if task is None:
        from nova_core.schemas.errors import NotFoundError

        raise NotFoundError("coding_task", task_id)
    return CodingTaskResponse(
        task_id=task.id,
        stage=task.stage,
        timeline=task.timeline or [],
        summary=task.summary,
        approval_id=task.approval_id,
    )
