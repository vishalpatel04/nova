"""Local memory kernel API routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import require_roles
from apps.api.deps import get_db_session
from apps.api.services.memory_kernel import MemoryKernelService
from nova_core.auth.principal import Principal
from nova_core.memory.access_policy import AccessProfile
from nova_core.models.orm import MemoryFact, MemoryRelationship
from nova_core.schemas.api import (
    MemoryAccessProfileRequest,
    MemoryAuditIntegrityResponse,
    MemoryExportResponse,
    MemoryFactResponse,
    MemoryFolderRequest,
    MemoryForgetTopicRequest,
    MemoryOverviewResponse,
    MemoryRelationshipResponse,
    MemoryRememberRequest,
    MemorySearchHitResponse,
    MemorySearchRequest,
    MemorySearchResponse,
)
from nova_core.schemas.settings import get_settings

router = APIRouter(prefix="/memory", tags=["memory"])


def _kernel(session: AsyncSession) -> MemoryKernelService:
    return MemoryKernelService(session, get_settings())


@router.get("/overview", response_model=MemoryOverviewResponse)
async def memory_overview(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> MemoryOverviewResponse:
    svc = _kernel(session)
    data = await svc.status_overview(principal.user_id)
    return MemoryOverviewResponse(**data)


@router.post("/profile", response_model=MemoryOverviewResponse)
async def set_access_profile(
    body: MemoryAccessProfileRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> MemoryOverviewResponse:
    try:
        profile = AccessProfile(body.profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    svc = _kernel(session)
    await svc.set_access_profile(principal.user_id, profile)
    await session.commit()
    data = await svc.status_overview(principal.user_id)
    return MemoryOverviewResponse(**data)


@router.post("/scan")
async def scan_sources(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    svc = _kernel(session)
    result = await svc.scan_sources(principal.user_id)
    await session.commit()
    return result


@router.post("/pause")
async def pause_indexing(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    svc = _kernel(session)
    await svc.pause_indexing(principal.user_id)
    await session.commit()
    return {"status": "paused"}


@router.post("/resume")
async def resume_indexing(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    svc = _kernel(session)
    await svc.resume_indexing(principal.user_id)
    await session.commit()
    return {"status": "resumed"}


@router.post("/include-folder")
async def include_folder(
    body: MemoryFolderRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    svc = _kernel(session)
    try:
        await svc.add_searchable_folder(principal.user_id, body.path)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await session.commit()
    return {"status": "included", "path": body.path}


@router.post("/exclude-folder")
async def exclude_folder(
    body: MemoryFolderRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    svc = _kernel(session)
    try:
        await svc.exclude_folder(principal.user_id, body.path)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await session.commit()
    return {"status": "excluded", "path": body.path}


@router.post("/search", response_model=MemorySearchResponse)
async def search_memory(
    body: MemorySearchRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> MemorySearchResponse:
    svc = _kernel(session)
    result = await svc.retrieve(principal.user_id, body.query, limit=body.limit)
    await session.commit()
    return MemorySearchResponse(
        query=result.query,
        hits=[
            MemorySearchHitResponse(
                kind=h.kind,
                memory_id=h.memory_id,
                summary=h.summary,
                score=h.score,
                provenance=h.provenance,
            )
            for h in result.hits
        ],
        semantic_available=result.semantic_available,
        searched_sources=result.searched_sources,
    )


@router.get("/facts", response_model=list[MemoryFactResponse])
async def list_facts(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> list[MemoryFactResponse]:
    result = await session.execute(
        select(MemoryFact).where(
            MemoryFact.user_id == principal.user_id,
            MemoryFact.valid_until.is_(None),
        )
    )
    return [
        MemoryFactResponse(
            id=f.id,
            subject=f.subject,
            predicate=f.predicate,
            object_summary=f.object_summary,
            confidence=f.confidence,
            user_confirmed=f.user_confirmed,
            project_root=f.project_root,
        )
        for f in result.scalars().all()
    ]


@router.get("/relationships", response_model=list[MemoryRelationshipResponse])
async def list_relationships(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> list[MemoryRelationshipResponse]:
    result = await session.execute(
        select(MemoryRelationship).where(
            MemoryRelationship.user_id == principal.user_id,
            MemoryRelationship.valid_until.is_(None),
        )
    )
    return [
        MemoryRelationshipResponse(
            id=r.id,
            relation_type=r.relation_type,
            confidence=r.confidence,
            source_entity_id=r.source_entity_id,
            target_entity_id=r.target_entity_id,
            user_confirmed=r.user_confirmed,
        )
        for r in result.scalars().all()
    ]


@router.post("/remember", response_model=MemoryFactResponse)
async def remember_fact(
    body: MemoryRememberRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> MemoryFactResponse:
    svc = _kernel(session)
    try:
        fact = await svc.remember_fact(
            principal.user_id,
            subject=body.subject,
            predicate=body.predicate,
            object_summary=body.object_summary,
            project_root=body.project_root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return MemoryFactResponse(
        id=fact.id,
        subject=fact.subject,
        predicate=fact.predicate,
        object_summary=fact.object_summary,
        confidence=fact.confidence,
        user_confirmed=fact.user_confirmed,
        project_root=fact.project_root,
    )


@router.post("/forget-topic")
async def forget_topic(
    body: MemoryForgetTopicRequest,
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    svc = _kernel(session)
    result = await svc.forget_topic(principal.user_id, body.topic)
    await session.commit()
    return result


@router.get("/export", response_model=MemoryExportResponse)
async def export_memory(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> MemoryExportResponse:
    svc = _kernel(session)
    data = await svc.export_memory(principal.user_id)
    return MemoryExportResponse(**data)


@router.get("/audit-integrity", response_model=MemoryAuditIntegrityResponse)
async def audit_integrity(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> MemoryAuditIntegrityResponse:
    svc = _kernel(session)
    valid = await svc.audit_integrity(principal.user_id)
    return MemoryAuditIntegrityResponse(valid=valid)


@router.post("/process-jobs")
async def process_jobs(
    principal: Annotated[Principal, Depends(require_roles("client"))],
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    svc = _kernel(session)
    count = await svc.process_pending_jobs(principal.user_id)
    await session.commit()
    return {"processed": count}
