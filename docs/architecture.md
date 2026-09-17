# Architecture

Authoritative source: `AGENT.md` §5, §8, §52. This file records deltas as the scaffold grows.

## Current state (scaffold)

```
Next.js (frontend)        FastAPI (backend)         Postgres + pgvector
     │                          │                          │
     └────── HTTP /api/v1 ──────┤                          │
                                │◀─── SQLAlchemy async ────┘
                                │
                                ├──▶ Redis (cache / queue substrate)
                                └──▶ MinIO (S3-compatible object storage)
```

- No auth layer yet. `/api/v1/projects`, `/documents`, `/sessions` all return 501.
- No agents implemented; `app/agents/base.py` defines the contract from §11.
- No LLM providers implemented; `app/providers/base.py` defines the contract from §7.

## Planned additions (in order)

1. Auth + user model (§41–42).
2. Preparation project + document entities (§51) with migrations.
3. Document ingest pipeline (§17) → Document Agent.
4. Knowledge extraction + embeddings (§20, retrieval §21).
5. Session + question/response entities → Examiner + Evaluator agents.
6. Alexa+ adapter (§31) once the web loop works end-to-end.

## Decisions to record here as they're made

- Readiness scoring formula (§27) — TBD, must be deterministic.
- Model routing table (§7 / §50) — TBD, per-task cost caps.
- Chunking strategy (§17) — TBD, per-document-type.
