"""Hybrid local memory retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nova_core.memory.embeddings import LocalEmbeddingAdapter, cosine_similarity
from nova_core.memory.vault import is_vault_path, sanitize_for_external_response
from nova_core.models.orm import (
    MemoryChunk,
    MemoryDocument,
    MemoryEntity,
    MemoryFact,
    MemoryRelationship,
)
from nova_core.schemas.settings import Settings


@dataclass(frozen=True)
class RetrievalHit:
    kind: str
    memory_id: str
    summary: str
    score: float
    provenance: str


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    hits: list[RetrievalHit]
    semantic_available: bool
    searched_sources: list[str]


def _tokenize(query: str) -> list[str]:
    return [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]


async def hybrid_retrieve(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: str,
    query: str,
    project_root: str | None = None,
    limit: int = 10,
) -> RetrievalResult:
    tokens = _tokenize(query)
    hits: list[RetrievalHit] = []

    fact_result = await session.execute(
        select(MemoryFact).where(
            MemoryFact.user_id == user_id,
            MemoryFact.valid_until.is_(None),
        )
    )
    for fact in fact_result.scalars().all():
        hay = f"{fact.subject} {fact.predicate} {fact.object_summary}".lower()
        score = sum(1 for t in tokens if t in hay) / max(len(tokens), 1)
        if project_root and fact.project_root and fact.project_root != project_root:
            score *= 0.5
        if score > 0:
            hits.append(
                RetrievalHit(
                    kind="fact",
                    memory_id=fact.id,
                    summary=f"{fact.subject} {fact.predicate} {fact.object_summary}",
                    score=score + (0.2 if fact.user_confirmed else 0),
                    provenance="memory_facts",
                )
            )

    doc_result = await session.execute(
        select(MemoryDocument).where(
            MemoryDocument.user_id == user_id,
            MemoryDocument.deleted_at.is_(None),
        )
    )
    searched_sources: set[str] = set()
    for doc in doc_result.scalars().all():
        if is_vault_path(doc.canonical_path):
            continue
        searched_sources.add(doc.source_id)
        hay = f"{doc.filename} {doc.relative_path}".lower()
        score = sum(1 for t in tokens if t in hay) / max(len(tokens), 1)
        if score > 0:
            hits.append(
                RetrievalHit(
                    kind="document",
                    memory_id=doc.id,
                    summary=sanitize_for_external_response(doc.canonical_path),
                    score=score,
                    provenance="memory_documents",
                )
            )

    chunk_result = await session.execute(select(MemoryChunk).where(MemoryChunk.user_id == user_id))
    chunks = list(chunk_result.scalars().all())
    embedder = LocalEmbeddingAdapter(settings)
    health = await embedder.health()
    query_vec: list[float] | None = None
    if health.available:
        query_vec = await embedder.embed_text(query)

    for chunk in chunks:
        if is_vault_path(chunk.text_summary):
            continue
        kw_score = 0.0
        if chunk.keyword_text:
            hay = chunk.keyword_text.lower()
            kw_score = sum(1 for t in tokens if t in hay) / max(len(tokens), 1)
        sem_score = 0.0
        if query_vec and chunk.embedding_json:
            sem_score = cosine_similarity(query_vec, chunk.embedding_json)
        score = max(kw_score, sem_score)
        if project_root and chunk.project_root and chunk.project_root != project_root:
            score *= 0.6
        if score > 0.05:
            hits.append(
                RetrievalHit(
                    kind="chunk",
                    memory_id=chunk.id,
                    summary=chunk.text_summary[:240],
                    score=score,
                    provenance="memory_chunks",
                )
            )

    rel_result = await session.execute(
        select(MemoryRelationship).where(MemoryRelationship.user_id == user_id)
    )
    entity_names: dict[str, str] = {}
    ent_result = await session.execute(
        select(MemoryEntity).where(MemoryEntity.user_id == user_id)
    )
    for ent in ent_result.scalars().all():
        entity_names[ent.id] = ent.canonical_name
    for rel in rel_result.scalars().all():
        if rel.valid_until is not None:
            continue
        src = entity_names.get(rel.source_entity_id, "")
        tgt = entity_names.get(rel.target_entity_id, "")
        hay = f"{src} {tgt} {rel.relation_type}".lower()
        score = sum(1 for t in tokens if t in hay) / max(len(tokens), 1)
        if score <= 0:
            continue
        hits.append(
            RetrievalHit(
                kind="relationship",
                memory_id=rel.id,
                summary=f"{src} {rel.relation_type} {tgt} (confidence {rel.confidence:.2f})",
                score=score,
                provenance="memory_relationships",
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return RetrievalResult(
        query=query,
        hits=hits[:limit],
        semantic_available=health.available,
        searched_sources=sorted(searched_sources),
    )


def format_retrieval_result(result: RetrievalResult) -> str:
    if not result.hits:
        msg = f'No local memory matches for "{result.query}".'
        if not result.semantic_available:
            msg += "\nSemantic indexing unavailable — install local embedding model."
        return msg
    lines = [f'Found {len(result.hits)} local memory matches for "{result.query}".']
    if not result.semantic_available:
        lines.append("Semantic indexing unavailable — keyword/metadata search only.")
    for hit in result.hits[:5]:
        lines.append(f"- [{hit.kind}] {hit.summary} (score {hit.score:.2f}, {hit.provenance})")
    return "\n".join(lines)


def build_memory_prompt_section(result: RetrievalResult, *, max_chars: int = 1500) -> str:
    if not result.hits:
        return ""
    lines = ["Local memory retrieval:"]
    used = 0
    for hit in result.hits[:5]:
        line = f"- {hit.summary} ({hit.provenance})"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)
