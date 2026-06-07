"""Agent plan orchestration API routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.agent_plans import AgentPlanService
from apps.api.services.git_workflow import GitWorkflowService
from apps.api.services.patch_executions import PatchExecutionService
from nova_core.auth.principal import Principal
from nova_core.schemas.settings import get_settings

router = APIRouter(tags=["agent-plans"])


class CreateAgentPlanRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=2000)
    title: str | None = None
    project_root: str | None = None
    draft: bool = False


class RetryStepRequest(BaseModel):
    step_index: int = Field(ge=0, le=7)


class ProposeBranchRequest(BaseModel):
    project_root: str
    branch_name: str = Field(min_length=1, max_length=64)


class ProposeCommitRequest(BaseModel):
    project_root: str
    commit_message: str = Field(min_length=1, max_length=500)
    staged_paths: list[str] = Field(min_length=1)


class ApprovalIdRequest(BaseModel):
    approval_id: str = Field(min_length=36, max_length=36)


@router.post("/agent-plans")
async def create_agent_plan(
    body: CreateAgentPlanRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = AgentPlanService(session, get_settings())
    plan = await svc.create_plan(
        principal,
        objective=body.objective,
        title=body.title,
        draft=body.draft,
        project_root=body.project_root,
    )
    steps = await svc._load_steps(plan.id)
    await session.commit()
    return svc._plan_response(plan, steps)


@router.get("/agent-plans/active")
async def get_active_agent_plan(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = AgentPlanService(session, get_settings())
    plan = await svc.get_active_plan(principal)
    if plan is None:
        return {"plan": None}
    steps = await svc._load_steps(plan.id)
    return {"plan": svc._plan_response(plan, steps)}


@router.get("/agent-plans/{plan_id}")
async def get_agent_plan(
    plan_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = AgentPlanService(session, get_settings())
    plan = await svc.get_plan(principal, plan_id)
    if plan is None:
        return {"plan": None}
    steps = await svc._load_steps(plan.id)
    return {"plan": svc._plan_response(plan, steps)}


@router.get("/agent-plans")
async def list_agent_plans(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = AgentPlanService(session, get_settings())
    plans = await svc.list_plans(principal)
    return {
        "plans": [
            {
                "id": p.id,
                "title": p.title,
                "status": p.status,
                "provider_lane": p.provider_lane,
                "created_at": p.created_at.isoformat(),
            }
            for p in plans
        ]
    }


@router.post("/agent-plans/{plan_id}/run")
async def run_agent_plan(
    plan_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = AgentPlanService(session, get_settings())
    result = await svc.run_plan(principal, plan_id)
    await session.commit()
    return result


@router.post("/agent-plans/{plan_id}/cancel")
async def cancel_agent_plan(
    plan_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = AgentPlanService(session, get_settings())
    plan = await svc.cancel_plan(principal, plan_id)
    await session.commit()
    return {"plan_id": plan.id, "status": plan.status}


@router.post("/agent-plans/{plan_id}/retry-step")
async def retry_agent_plan_step(
    plan_id: str,
    body: RetryStepRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = AgentPlanService(session, get_settings())
    result = await svc.retry_step(principal, plan_id, body.step_index)
    await session.commit()
    return result


@router.post("/agent-plans/{plan_id}/continue-after-patch")
async def continue_plan_after_patch(
    plan_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = AgentPlanService(session, get_settings())
    result = await svc.continue_after_patch_apply(principal, plan_id)
    await session.commit()
    return result


@router.get("/provider-trust")
async def provider_trust_status(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    _ = principal, session
    svc = AgentPlanService(session, get_settings())
    return svc.provider_lane_info()


@router.get("/git/status")
async def git_status(
    project_root: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = GitWorkflowService(session, get_settings())
    return await svc.git_status(principal, project_root)


@router.get("/git/diff-stat")
async def git_diff_stat(
    project_root: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = GitWorkflowService(session, get_settings())
    return await svc.git_diff_stat(principal, project_root)


@router.post("/git/propose-branch")
async def git_propose_branch(
    body: ProposeBranchRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = GitWorkflowService(session, get_settings())
    result = await svc.propose_branch(
        principal, project_root=body.project_root, branch_name=body.branch_name
    )
    await session.commit()
    return result


@router.post("/git/create-branch")
async def git_create_branch(
    body: ApprovalIdRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = GitWorkflowService(session, get_settings())
    result = await svc.create_approved_branch(principal, body.approval_id)
    await session.commit()
    return result


@router.post("/git/propose-commit")
async def git_propose_commit(
    body: ProposeCommitRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = GitWorkflowService(session, get_settings())
    result = await svc.propose_commit(
        principal,
        project_root=body.project_root,
        commit_message=body.commit_message,
        staged_paths=body.staged_paths,
    )
    await session.commit()
    return result


@router.post("/git/commit")
async def git_commit(
    body: ApprovalIdRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = GitWorkflowService(session, get_settings())
    result = await svc.commit_approved(principal, body.approval_id)
    await session.commit()
    return result


@router.post("/git/push")
async def git_push_blocked(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = GitWorkflowService(session, get_settings())
    return await svc.git_push_blocked(principal)


@router.post("/executions/apply-patch")
async def apply_patch_with_plan_continue(
    body: ApprovalIdRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
    plan_id: str | None = None,
) -> dict[str, Any]:
    patch_svc = PatchExecutionService(session, get_settings())
    execution = await patch_svc.apply_approved_patch(principal, body.approval_id)
    response: dict[str, Any] = {
        "execution_id": execution.id,
        "status": execution.status,
        "applied_files": execution.applied_files or [],
    }
    if plan_id:
        plan_svc = AgentPlanService(session, get_settings())
        plan_result = await plan_svc.continue_after_patch_apply(principal, plan_id)
        response["plan"] = plan_result
    await session.commit()
    return response
