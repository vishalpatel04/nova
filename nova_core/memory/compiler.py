"""Background memory compiler — bounded maintenance ticks."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.memory_kernel import MemoryKernelService
from nova_core.memory.vault import is_vault_path
from nova_core.models.enums import MemoryIndexJobStatus
from nova_core.models.orm import MemoryChunk, MemoryDocument, MemoryFact, MemoryIndexJob
from nova_core.schemas.settings import Settings
from nova_core.utils.time import utc_now


class MemoryCompiler:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.kernel = MemoryKernelService(session, settings)

    async def tick(
        self, user_id: str, *, job_limit: int = 10, scan_limit: int = 50
    ) -> dict[str, int]:
        cfg = await self.kernel.get_or_create_settings(user_id)
        if cfg.indexing_paused:
            return {"processed_jobs": 0, "discovered": 0, "superseded": 0}
        processed = await self.kernel.process_pending_jobs(user_id, limit=job_limit)
        scan = await self.kernel.scan_sources(user_id, max_files=scan_limit)
        superseded = await self._supersede_duplicate_facts(user_id)
        await self._purge_deleted_document_chunks(user_id)
        return {
            "processed_jobs": processed,
            "discovered": scan.get("discovered", 0),
            "superseded": superseded,
        }

    async def _supersede_duplicate_facts(self, user_id: str) -> int:
        result = await self.session.execute(
            select(MemoryFact).where(
                MemoryFact.user_id == user_id,
                MemoryFact.valid_until.is_(None),
            )
        )
        facts = list(result.scalars().all())
        seen: dict[tuple[str, str], MemoryFact] = {}
        count = 0
        for fact in facts:
            key = (fact.subject, fact.predicate)
            prior = seen.get(key)
            if prior and prior.object_summary != fact.object_summary:
                prior.valid_until = utc_now()
                count += 1
            seen[key] = fact
        await self.session.flush()
        return count

    async def _purge_deleted_document_chunks(self, user_id: str) -> None:
        docs = await self.session.execute(
            select(MemoryDocument).where(
                MemoryDocument.user_id == user_id,
                MemoryDocument.deleted_at.isnot(None),
            )
        )
        for doc in docs.scalars().all():
            if is_vault_path(doc.canonical_path):
                continue
            await self.session.execute(delete(MemoryChunk).where(MemoryChunk.document_id == doc.id))
        stale_jobs = await self.session.execute(
            select(MemoryIndexJob).where(
                MemoryIndexJob.user_id == user_id,
                MemoryIndexJob.status == MemoryIndexJobStatus.FAILED.value,
                MemoryIndexJob.attempts >= 5,
            )
        )
        for job in stale_jobs.scalars().all():
            job.status = MemoryIndexJobStatus.COMPLETED.value
        await self.session.flush()
