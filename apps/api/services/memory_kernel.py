"""Local memory kernel service — indexing, facts, graph, retrieval."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.auth.principal import Principal
from nova_core.memory.access_policy import AccessPolicy, AccessProfile, resolve_access_policy
from nova_core.memory.audit_chain import append_memory_audit, verify_audit_chain
from nova_core.memory.embeddings import LocalEmbeddingAdapter
from nova_core.memory.exclusions import is_text_extractable, should_skip_dir, should_skip_file
from nova_core.memory.extraction import chunk_text, extract_text
from nova_core.memory.paths import canonicalize_path
from nova_core.memory.retrieval import (
    RetrievalResult,
    hybrid_retrieve,
)
from nova_core.memory.vault import VAULT_INVISIBLE_MESSAGE, is_vault_path
from nova_core.models.enums import (
    MemoryAccessProfile,
    MemoryIndexingState,
    MemoryIndexJobStatus,
    MemoryIndexJobType,
    MemorySourceStatus,
    MemorySourceType,
)
from nova_core.models.orm import (
    MemoryChunk,
    MemoryDocument,
    MemoryEntity,
    MemoryEvent,
    MemoryFact,
    MemoryIndexJob,
    MemoryRelationship,
    MemoryRetrievalLog,
    MemorySource,
    MemoryUserSettings,
)
from nova_core.schemas.settings import Settings
from nova_core.utils.time import utc_now

MAX_FILES_PER_SCAN = 200


class MemoryKernelService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._embedder = LocalEmbeddingAdapter(settings)

    async def get_or_create_settings(self, user_id: str) -> MemoryUserSettings:
        result = await self.session.execute(
            select(MemoryUserSettings).where(MemoryUserSettings.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = MemoryUserSettings(
                user_id=user_id,
                access_profile=MemoryAccessProfile.MINIMAL.value,
            )
            self.session.add(record)
            await self.session.flush()
        return record

    async def get_access_policy(self, user_id: str) -> AccessPolicy:
        cfg = await self.get_or_create_settings(user_id)
        return resolve_access_policy(
            profile=cfg.access_profile,
            include_paths=cfg.custom_include_json or [],
            exclude_paths=cfg.custom_exclude_json or [],
            override_performance=cfg.override_performance_exclusions,
            indexing_paused=cfg.indexing_paused,
        )

    async def set_access_profile(
        self,
        user_id: str,
        profile: AccessProfile,
    ) -> MemoryUserSettings:
        cfg = await self.get_or_create_settings(user_id)
        cfg.access_profile = profile.value
        cfg.updated_at = utc_now()
        await self.sync_sources(user_id)
        await append_memory_audit(
            self.session,
            user_id=user_id,
            event_type="access_profile.changed",
            payload={"profile": profile.value},
        )
        await self.session.flush()
        return cfg

    async def sync_sources(self, user_id: str) -> list[MemorySource]:
        policy = await self.get_access_policy(user_id)
        existing = await self.session.execute(
            select(MemorySource).where(MemorySource.user_id == user_id)
        )
        by_path = {s.canonical_root_path: s for s in existing.scalars().all()}
        synced: list[MemorySource] = []
        for root in policy.allowed_roots():
            canonical = str(root)
            if is_vault_path(canonical):
                continue
            record = by_path.get(canonical)
            source_type = (
                MemorySourceType.HOME_DIRECTORY.value
                if policy.profile == AccessProfile.BROAD_LOCAL and root == Path.home().resolve()
                else MemorySourceType.PERSONAL_FOLDER.value
            )
            if record is None:
                record = MemorySource(
                    user_id=user_id,
                    root_path=str(root),
                    canonical_root_path=canonical,
                    source_type=source_type,
                    profile_origin=policy.profile.value,
                    content_indexing_enabled=not policy.indexing_paused,
                    status=MemorySourceStatus.ACTIVE.value,
                )
                self.session.add(record)
            else:
                record.status = (
                    MemorySourceStatus.PAUSED.value
                    if policy.indexing_paused
                    else MemorySourceStatus.ACTIVE.value
                )
                record.profile_origin = policy.profile.value
            synced.append(record)
        await self.session.flush()
        return synced

    async def scan_sources(
        self,
        user_id: str,
        *,
        max_files: int = MAX_FILES_PER_SCAN,
    ) -> dict[str, Any]:
        if is_vault_path(str(Path.home() / "NOVA_VAULT")):
            pass  # vault root never scanned
        policy = await self.get_access_policy(user_id)
        if policy.indexing_paused:
            return {"discovered": 0, "paused": True}
        sources = await self.sync_sources(user_id)
        discovered = 0
        override = policy.override_performance_exclusions
        for source in sources:
            if source.status != MemorySourceStatus.ACTIVE.value:
                continue
            root = Path(source.canonical_root_path)
            if not root.exists():
                continue
            for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                if discovered >= max_files:
                    break
                dirnames[:] = [
                    d for d in dirnames if not should_skip_dir(d, override_performance=override)
                ]
                if any(is_vault_path(str(Path(dirpath) / d)) for d in dirnames):
                    dirnames.clear()
                for name in filenames:
                    if discovered >= max_files:
                        break
                    full = Path(dirpath) / name
                    if is_vault_path(str(full)):
                        continue
                    if not policy.is_path_allowed(str(full)):
                        continue
                    if should_skip_file(full, override_performance=override):
                        await self._upsert_metadata_only(user_id, source, full)
                        discovered += 1
                        continue
                    await self._upsert_document(user_id, source, full, policy)
                    discovered += 1
            source.last_scan_at = utc_now()
        await append_memory_audit(
            self.session,
            user_id=user_id,
            event_type="index.scan_completed",
            payload={"discovered": discovered},
        )
        await self.session.flush()
        return {"discovered": discovered, "paused": False}

    async def _upsert_metadata_only(self, user_id: str, source: MemorySource, path: Path) -> None:
        canonical = canonicalize_path(str(path))
        if canonical is None:
            return
        rel = str(canonical.resolved.relative_to(Path(source.canonical_root_path)))
        content_hash = self._file_hash(path)
        existing = await self._find_document(user_id, canonical.canonical)
        if existing:
            existing.content_hash = content_hash
            existing.indexing_state = MemoryIndexingState.METADATA_ONLY.value
            return
        self.session.add(
            MemoryDocument(
                user_id=user_id,
                source_id=source.id,
                canonical_path=canonical.canonical,
                relative_path=rel,
                filename=path.name,
                extension=path.suffix.lower() or None,
                size_bytes=path.stat().st_size if path.exists() else None,
                modified_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                if path.exists()
                else None,
                content_hash=content_hash,
                indexing_state=MemoryIndexingState.METADATA_ONLY.value,
            )
        )

    async def _upsert_document(
        self, user_id: str, source: MemorySource, path: Path, policy: AccessPolicy
    ) -> None:
        canonical = canonicalize_path(str(path))
        if canonical is None:
            return
        rel = str(canonical.resolved.relative_to(Path(source.canonical_root_path)))
        content_hash = self._file_hash(path)
        existing = await self._find_document(user_id, canonical.canonical)
        state = MemoryIndexingState.PENDING_DEEP.value
        if not is_text_extractable(path):
            state = MemoryIndexingState.METADATA_ONLY.value
        if existing:
            if existing.content_hash == content_hash:
                return
            existing.content_hash = content_hash
            existing.indexing_state = state
            doc = existing
        else:
            doc = MemoryDocument(
                user_id=user_id,
                source_id=source.id,
                canonical_path=canonical.canonical,
                relative_path=rel,
                filename=path.name,
                extension=path.suffix.lower() or None,
                size_bytes=path.stat().st_size,
                modified_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
                content_hash=content_hash,
                indexing_state=state,
            )
            self.session.add(doc)
            await self.session.flush()
        if state == MemoryIndexingState.PENDING_DEEP.value:
            self.session.add(
                MemoryIndexJob(
                    user_id=user_id,
                    document_id=doc.id,
                    source_id=source.id,
                    job_type=MemoryIndexJobType.EXTRACT.value,
                    status=MemoryIndexJobStatus.PENDING.value,
                )
            )

    async def _find_document(self, user_id: str, canonical_path: str) -> MemoryDocument | None:
        result = await self.session.execute(
            select(MemoryDocument).where(
                MemoryDocument.user_id == user_id,
                MemoryDocument.canonical_path == canonical_path,
                MemoryDocument.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    def _file_hash(self, path: Path) -> str:
        try:
            stat = path.stat()
            payload = f"{path}:{stat.st_size}:{stat.st_mtime_ns}"
            return hashlib.sha256(payload.encode()).hexdigest()
        except OSError:
            return hashlib.sha256(str(path).encode()).hexdigest()

    async def process_pending_jobs(self, user_id: str, *, limit: int = 20) -> int:
        result = await self.session.execute(
            select(MemoryIndexJob)
            .where(
                MemoryIndexJob.user_id == user_id,
                MemoryIndexJob.status == MemoryIndexJobStatus.PENDING.value,
            )
            .limit(limit)
        )
        processed = 0
        for job in result.scalars().all():
            job.status = MemoryIndexJobStatus.RUNNING.value
            try:
                if job.document_id:
                    await self._deep_index_document(job.document_id)
                job.status = MemoryIndexJobStatus.COMPLETED.value
                processed += 1
            except Exception as exc:
                job.status = MemoryIndexJobStatus.FAILED.value
                job.last_error = str(exc)[:500]
                job.attempts += 1
        await self.session.flush()
        return processed

    async def _deep_index_document(self, document_id: str) -> None:
        doc = await self.session.get(MemoryDocument, document_id)
        if doc is None or is_vault_path(doc.canonical_path):
            return
        path = Path(doc.canonical_path)
        extracted = extract_text(path)
        if extracted is None:
            doc.indexing_state = MemoryIndexingState.SKIPPED.value
            return
        await self.session.execute(delete(MemoryChunk).where(MemoryChunk.document_id == doc.id))
        chunks = chunk_text(extracted.text)
        vectors = await self._embedder.embed_texts(chunks)
        for text, vec in zip(chunks, vectors, strict=False):
            self.session.add(
                MemoryChunk(
                    user_id=doc.user_id,
                    document_id=doc.id,
                    source_type="document",
                    source_id=doc.source_id,
                    text_summary=text,
                    keyword_text=text.lower(),
                    embedding_json=vec,
                )
            )
        doc.indexing_state = MemoryIndexingState.INDEXED.value
        doc.mime_type = extracted.mime_type

    async def remember_fact(
        self,
        user_id: str,
        *,
        subject: str,
        predicate: str,
        object_summary: str,
        user_confirmed: bool = True,
        project_root: str | None = None,
    ) -> MemoryFact:
        if any(x in f"{subject} {object_summary}".lower() for x in ("password", "token", "secret")):
            raise ValueError("Refusing to store secret-like memory.")
        result = await self.session.execute(
            select(MemoryFact).where(
                MemoryFact.user_id == user_id,
                MemoryFact.subject == subject.lower(),
                MemoryFact.predicate == predicate,
                MemoryFact.valid_until.is_(None),
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.valid_until = utc_now()
        fact = MemoryFact(
            user_id=user_id,
            project_root=project_root,
            subject=subject.lower(),
            predicate=predicate,
            object_summary=object_summary,
            user_confirmed=user_confirmed,
            valid_from=utc_now(),
        )
        self.session.add(fact)
        await self._ensure_graph_for_fact(fact)
        await append_memory_audit(
            self.session,
            user_id=user_id,
            event_type="memory.fact.remembered",
            payload={"subject": subject, "predicate": predicate},
        )
        await self.session.flush()
        return fact

    async def _ensure_graph_for_fact(self, fact: MemoryFact) -> None:
        subj = await self._get_or_create_entity(fact.user_id, "topic", fact.subject)
        obj = await self._get_or_create_entity(
            fact.user_id,
            "folder" if fact.predicate == "stored_in" else "topic",
            fact.object_summary,
        )
        self.session.add(
            MemoryRelationship(
                user_id=fact.user_id,
                source_entity_id=subj.id,
                relation_type=fact.predicate,
                target_entity_id=obj.id,
                confidence=fact.confidence,
                user_confirmed=fact.user_confirmed,
                valid_from=utc_now(),
            )
        )

    async def _get_or_create_entity(
        self, user_id: str, entity_type: str, name: str
    ) -> MemoryEntity:
        normalized = name.strip().lower()
        result = await self.session.execute(
            select(MemoryEntity).where(
                MemoryEntity.user_id == user_id,
                MemoryEntity.canonical_name == normalized,
            )
        )
        entity = result.scalar_one_or_none()
        if entity:
            return entity
        entity = MemoryEntity(
            user_id=user_id,
            entity_type=entity_type,
            canonical_name=normalized,
        )
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def forget_topic(self, user_id: str, topic: str) -> dict[str, int]:
        topic_l = topic.lower()
        facts = await self.session.execute(select(MemoryFact).where(MemoryFact.user_id == user_id))
        fact_count = 0
        for fact in facts.scalars().all():
            if topic_l in fact.subject or topic_l in fact.object_summary.lower():
                fact.valid_until = utc_now()
                fact_count += 1
        chunks = await self.session.execute(
            select(MemoryChunk).where(MemoryChunk.user_id == user_id)
        )
        chunk_count = 0
        for chunk in chunks.scalars().all():
            if topic_l in chunk.text_summary.lower():
                await self.session.delete(chunk)
                chunk_count += 1
        entities = await self.session.execute(
            select(MemoryEntity).where(MemoryEntity.user_id == user_id)
        )
        entity_ids: set[str] = set()
        for entity in entities.scalars().all():
            if topic_l in entity.canonical_name:
                entity_ids.add(entity.id)
        rel_count = 0
        if entity_ids:
            rels = await self.session.execute(
                select(MemoryRelationship).where(MemoryRelationship.user_id == user_id)
            )
            for rel in rels.scalars().all():
                if rel.valid_until is not None:
                    continue
                if rel.source_entity_id in entity_ids or rel.target_entity_id in entity_ids:
                    rel.valid_until = utc_now()
                    rel_count += 1
        await append_memory_audit(
            self.session,
            user_id=user_id,
            event_type="memory.topic.forgotten",
            payload={
                "topic": topic,
                "facts": fact_count,
                "chunks": chunk_count,
                "relationships": rel_count,
            },
        )
        await self.session.flush()
        return {"facts": fact_count, "chunks": chunk_count, "relationships": rel_count}

    async def retrieve(
        self,
        user_id: str,
        query: str,
        *,
        session_id: str | None = None,
        project_root: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        result = await hybrid_retrieve(
            self.session,
            self.settings,
            user_id=user_id,
            query=query,
            project_root=project_root,
            limit=limit,
        )
        self.session.add(
            MemoryRetrievalLog(
                user_id=user_id,
                session_id=session_id,
                query_summary=query[:512],
                selected_memory_ids_json=[h.memory_id for h in result.hits],
                scores_json={h.memory_id: h.score for h in result.hits},
            )
        )
        await self.session.flush()
        return result

    async def status_overview(self, user_id: str) -> dict[str, Any]:
        cfg = await self.get_or_create_settings(user_id)
        embed_health = await self._embedder.health()
        doc_count = await self.session.scalar(
            select(func.count())
            .select_from(MemoryDocument)
            .where(MemoryDocument.user_id == user_id, MemoryDocument.deleted_at.is_(None))
        )
        indexed = await self.session.scalar(
            select(func.count())
            .select_from(MemoryDocument)
            .where(
                MemoryDocument.user_id == user_id,
                MemoryDocument.indexing_state == MemoryIndexingState.INDEXED.value,
            )
        )
        chunk_count = await self.session.scalar(
            select(func.count()).select_from(MemoryChunk).where(MemoryChunk.user_id == user_id)
        )
        entity_count = await self.session.scalar(
            select(func.count()).select_from(MemoryEntity).where(MemoryEntity.user_id == user_id)
        )
        rel_count = await self.session.scalar(
            select(func.count())
            .select_from(MemoryRelationship)
            .where(MemoryRelationship.user_id == user_id)
        )
        pending_jobs = await self.session.scalar(
            select(func.count())
            .select_from(MemoryIndexJob)
            .where(
                MemoryIndexJob.user_id == user_id,
                MemoryIndexJob.status == MemoryIndexJobStatus.PENDING.value,
            )
        )
        sources = await self.session.execute(
            select(MemorySource).where(MemorySource.user_id == user_id)
        )
        return {
            "access_profile": cfg.access_profile,
            "indexing_paused": cfg.indexing_paused,
            "local_only": True,
            "documents_discovered": doc_count or 0,
            "documents_indexed": indexed or 0,
            "chunks": chunk_count or 0,
            "entities": entity_count or 0,
            "relationships": rel_count or 0,
            "pending_jobs": pending_jobs or 0,
            "embedding_health": embed_health.message,
            "embedding_available": embed_health.available,
            "sources": [
                {
                    "id": s.id,
                    "root_path": s.root_path,
                    "status": s.status,
                    "last_scan_at": s.last_scan_at.isoformat() if s.last_scan_at else None,
                }
                for s in sources.scalars().all()
                if not is_vault_path(s.root_path)
            ],
            "vault_path": str(Path.home() / "NOVA_VAULT"),
            "vault_invisible": True,
        }

    async def export_memory(self, user_id: str) -> dict[str, Any]:
        facts = await self.session.execute(
            select(MemoryFact).where(
                MemoryFact.user_id == user_id, MemoryFact.valid_until.is_(None)
            )
        )
        entities = await self.session.execute(
            select(MemoryEntity).where(MemoryEntity.user_id == user_id)
        )
        relationships = await self.session.execute(
            select(MemoryRelationship).where(MemoryRelationship.user_id == user_id)
        )
        return {
            "exported_at": utc_now().isoformat(),
            "local_only": True,
            "facts": [
                {
                    "subject": f.subject,
                    "predicate": f.predicate,
                    "object": f.object_summary,
                    "confirmed": f.user_confirmed,
                }
                for f in facts.scalars().all()
            ],
            "entities": [
                {"type": e.entity_type, "name": e.canonical_name} for e in entities.scalars().all()
            ],
            "relationships": [
                {
                    "type": r.relation_type,
                    "confidence": r.confidence,
                    "source_entity_id": r.source_entity_id,
                    "target_entity_id": r.target_entity_id,
                }
                for r in relationships.scalars().all()
            ],
        }

    async def audit_integrity(self, user_id: str) -> bool:
        return await verify_audit_chain(self.session, user_id)

    async def record_project_event(
        self,
        principal: Principal,
        *,
        project_root: str,
        event_type: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        if is_vault_path(project_root):
            raise PermissionError(VAULT_INVISIBLE_MESSAGE)
        event = MemoryEvent(
            user_id=principal.user_id,
            device_id=principal.device_id,
            event_type=event_type,
            project_root=project_root,
            summary=summary,
            metadata_json=metadata,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_project_events(
        self, user_id: str, project_root: str, *, limit: int = 20
    ) -> list[MemoryEvent]:
        result = await self.session.execute(
            select(MemoryEvent)
            .where(
                MemoryEvent.user_id == user_id,
                MemoryEvent.project_root == project_root,
            )
            .order_by(MemoryEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def format_project_history(self, user_id: str, project_root: str) -> str:
        events = await self.list_project_events(user_id, project_root)
        if not events:
            return "No project history recorded yet."
        lines = [f"Project history for {project_root}:"]
        for ev in reversed(events):
            lines.append(f"- [{ev.event_type}] {ev.summary}")
        return "\n".join(lines)

    async def pause_indexing(self, user_id: str) -> None:
        cfg = await self.get_or_create_settings(user_id)
        cfg.indexing_paused = True
        await self.sync_sources(user_id)

    async def resume_indexing(self, user_id: str) -> None:
        cfg = await self.get_or_create_settings(user_id)
        cfg.indexing_paused = False
        await self.sync_sources(user_id)

    async def add_searchable_folder(self, user_id: str, path: str) -> None:
        if is_vault_path(path):
            raise PermissionError(VAULT_INVISIBLE_MESSAGE)
        cfg = await self.get_or_create_settings(user_id)
        includes = list(cfg.custom_include_json or [])
        if path not in includes:
            includes.append(path)
        cfg.custom_include_json = includes
        cfg.access_profile = MemoryAccessProfile.CUSTOM.value
        await self.sync_sources(user_id)

    async def exclude_folder(self, user_id: str, path: str) -> None:
        if is_vault_path(path):
            raise PermissionError(VAULT_INVISIBLE_MESSAGE)
        cfg = await self.get_or_create_settings(user_id)
        excludes = list(cfg.custom_exclude_json or [])
        if path not in excludes:
            excludes.append(path)
        cfg.custom_exclude_json = excludes
        await self.sync_sources(user_id)
