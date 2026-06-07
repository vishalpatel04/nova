"""Controlled execution API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.executions import ControlledExecutionService
from nova_core.auth.principal import Principal
from nova_core.models.orm import ShellExecution
from nova_core.schemas.api import RunApprovedExecutionRequest, ShellExecutionResponse
from nova_core.schemas.settings import get_settings

router = APIRouter(prefix="/executions", tags=["executions"])


def _execution_response(record: ShellExecution) -> ShellExecutionResponse:
    return ShellExecutionResponse(
        execution_id=record.id,
        approval_id=record.approval_id,
        capability=record.capability,
        command_preview=record.command_preview,
        status=record.status,
        stdout_excerpt=record.stdout_excerpt,
        stderr_excerpt=record.stderr_excerpt,
        exit_code=record.exit_code,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


@router.post("/run-approved", response_model=ShellExecutionResponse)
async def run_approved_execution(
    body: RunApprovedExecutionRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> ShellExecutionResponse:
    settings = get_settings()
    svc = ControlledExecutionService(session, settings)
    record = await svc.run_approved(principal, body.approval_id)
    await session.commit()
    return _execution_response(record)
