"""Agent OS API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.agent_mission_service import AgentMissionService
from nova_core.auth.principal import Principal
from nova_core.schemas.settings import get_settings

router = APIRouter(prefix="/agent-os", tags=["agent-os"])


class CreateMissionRequest(BaseModel):
    request: str = Field(min_length=1)
    run_npm: bool = True
    clean_workspace: bool = False


class MissionResponse(BaseModel):
    mission_id: str
    status: str
    mission_type: str
    commander: str
    squad: list[str]
    workspace_path: str = ""
    preview_url: str | None = None
    final_report: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)


def _mission_response(mission: Any) -> MissionResponse:
    return MissionResponse(
        mission_id=mission.mission_id,
        status=mission.status.value if hasattr(mission.status, "value") else str(mission.status),
        mission_type=mission.mission_type,
        commander=mission.commander,
        squad=mission.squad,
        workspace_path=mission.workspace_path,
        preview_url=mission.preview_url,
        final_report=mission.final_report,
        timeline=[
            {
                "agent_id": e.agent_id,
                "display_name": e.display_name,
                "message": e.message,
                "timestamp": e.timestamp,
            }
            for e in mission.timeline_events
        ],
    )


@router.get("/status")
async def agent_os_status(
    principal: Annotated[Principal, Depends(require_roles("client"))],
) -> dict[str, Any]:
    return AgentMissionService.status_summary()


@router.get("/agents")
async def list_agents_route(
    principal: Annotated[Principal, Depends(require_roles("client"))],
) -> dict[str, Any]:
    return AgentMissionService.list_agent_catalog()


@router.get("/skills")
async def list_skills_route(
    principal: Annotated[Principal, Depends(require_roles("client"))],
) -> list[dict[str, Any]]:
    return AgentMissionService.list_skill_catalog()


@router.post("/missions", response_model=MissionResponse)
async def create_mission(
    body: CreateMissionRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> MissionResponse:
    svc = AgentMissionService(session, get_settings())
    mission = svc.run_mission(
        body.request,
        run_npm=body.run_npm,
        clean_workspace=body.clean_workspace,
    )
    await session.commit()
    return _mission_response(mission)


@router.get("/missions/{mission_id}", response_model=MissionResponse)
async def get_mission(
    mission_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> MissionResponse:
    svc = AgentMissionService(session, get_settings())
    mission = svc.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _mission_response(mission)


@router.get("/missions/{mission_id}/timeline")
async def mission_timeline(
    mission_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    svc = AgentMissionService(session, get_settings())
    return {"timeline": svc.mission_timeline_text(mission_id)}


@router.post("/missions/{mission_id}/approve", response_model=MissionResponse)
async def approve_mission(
    mission_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> MissionResponse:
    svc = AgentMissionService(session, get_settings())
    try:
        mission = svc.approve_deployment(mission_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return _mission_response(mission)


@router.post("/missions/{mission_id}/deploy", response_model=MissionResponse)
async def deploy_mission(
    mission_id: str,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> MissionResponse:
    svc = AgentMissionService(session, get_settings())
    try:
        mission = svc.deploy_mission(mission_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return _mission_response(mission)
