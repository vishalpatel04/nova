# NOVA Local Memory Kernel

Personal local-first memory: broad home indexing (except `~/NOVA_VAULT`), hybrid retrieval, project history, temporal graph, and Memory Center UI.

## Access policy

| Profile | Scope |
|---------|--------|
| `minimal` | Desktop, Documents, Downloads, Projects (default) |
| `broad_local` | Entire home directory except permanent exclusions |
| `custom` | Explicit include/exclude folders |

**Permanent hard exclusion:** `~/NOVA_VAULT` — invisible to search, indexing, metadata, embeddings, graph, watchers, shell, and external providers. No override.

**Performance exclusions** (node_modules, .venv, caches, large binaries) are skippable for speed; override via settings where safe.

### Enable broad local knowledge (Arth's machine)

Chat: `enable broad local knowledge`

API: `POST /api/v1/memory/profile` with `{"profile":"broad_local"}`

Memory Center → Indexed → Enable broad local knowledge

## Architecture

```
memory_sources → scan/index → memory_documents → memory_index_jobs
                                              ↓
                         extract → chunk → embed (Ollama nomic-embed-text)
                                              ↓
                    memory_facts / memory_entities / memory_relationships
                                              ↓
                         hybrid_retrieve → chat prompt injection / Memory Center
                                              ↓
                         memory_audit_chain (hash-chained tamper evidence)
```

## Embeddings

- Local Ollama only: `nomic-embed-text` (256 dims)
- Config: `NOVA_MEMORY_EMBEDDING_MODEL`, `NOVA_MEMORY_EMBEDDING_DIMENSIONS`
- Install: `ollama pull nomic-embed-text`
- Graceful degradation: metadata + keyword search continue if model unavailable

## Project history

Auto-captured events: branch changes, validation, patches, commits, milestones.

Chat commands: `show project history`, `what did we do yesterday?`, `continue from yesterday`, `what broke last time?`, `show open loops`, `remember this project decision: …`

## Graph memory

Postgres tables: `memory_entities`, `memory_relationships` with validity intervals, confidence, provenance, forget/supersede support.

## Hybrid retrieval

Fast path: facts, filenames, metadata, cached relationships.

Deep path: semantic vectors, keyword chunks, graph edges.

Prompt injection bounds (local provider only):

- Recent turns: max 16
- Facts: max 5
- Semantic chunks: max 5
- Relationships: max 8
- Total memory context: max 6000 chars

External providers receive **zero** memory by default.

## Memory compiler

Background tick (~45s): bounded scan, pending job processing, duplicate fact supersession, stale chunk cleanup.

Pause/resume via chat or API.

## Memory Center (macOS)

Settings → Memory tab: Overview, Indexed folders, Facts, Relationships, Search, Privacy (export, audit verify, vault explanation).

## Privacy

- Vault permanently invisible
- Local-only export JSON
- Forget topic / forget memory by id
- Hash-chained audit integrity check

## Startup

```bash
make migrate
make dev   # or docker compose up
ollama pull nomic-embed-text
```

## Validation

```bash
make lint && make typecheck && make test
bash scripts/demo_local_memory_kernel.sh
```

## Limitations

- PDF/docx/pptx/xlsx: metadata-only until local extractors added
- Full-home initial index is bounded per scan (200 files default)
- Graph visualization is list-first; node-link view optional later
- pgvector extension enabled on PostgreSQL; tests use JSON embeddings on SQLite

## Migration

Revision: `0014_local_memory_kernel` (≤32 chars, single Alembic head)
