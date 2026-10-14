# Architecture

How the pieces fit together today. The source of truth for behaviour is the test suite (`backend/tests/`, 108 passing); this doc explains the shape.

## Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Browser / MCP client                          │
│  • /mcp-tester web page (built-in MCP client, no external software) │
│  • Any Streamable HTTP MCP client (an Alexa+ simulator, custom)     │
│  • Session UI with mic + optional TTS                               │
└─────────────────────────────────────────────────────────────────────┘
                │                                 │
    HTTP /api/v1                     POST /api/v1/mcp/   (judged)
                │                     POST /api/v1/mcp-lab/ (lab)
                ▼                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI (backend)                           │
│                                                                     │
│  REST (/api/v1/…)              MCP mounts (ASGI, Streamable HTTP)   │
│  • auth / projects / docs      • /mcp/  . 7 prep.* tools (frozen)  │
│  • competencies / readiness    • /mcp-lab/. Same 7 + diagnostic;   │
│  • sessions / turns              honours X-LLM-Provider header      │
│  • admin / announcements                                            │
│  • demo seed / alexa webhook                                        │
│                                                                     │
│  Agents (deterministic by default, opt-in LLM enhancement):         │
│    Document · Knowledge Extraction · Examiner · Evaluator           │
│    Weakness · Adaptive Planner · Coach                              │
│                                                                     │
│  Providers (per-request swappable):                                 │
│    mock (default) · openai · bedrock                                │
└─────────────────────────────────────────────────────────────────────┘
       │                 │                   │                 │
       ▼                 ▼                   ▼                 ▼
   Postgres 16        Redis             MinIO / S3         Nginx + TLS
   + pgvector         (cache)           (uploads)          (edge)
```

## Request paths

### MCP (Alexa+ track submission surface)

`POST /api/v1/mcp/`. Streamable HTTP, MCP spec **2025-11-25**, stateless mode. Any compliant MCP client (web page, Alexa+ simulator, custom script) connects, authenticates with a Bearer JWT, calls `initialize` → `notifications/initialized` → `tools/list` → `tools/call`.

Seven tools cover the full preparation flow:

| Tool | Purpose |
|---|---|
| `prep.list_projects` | List the user's preparation projects. |
| `prep.extract_competencies` | Build / refresh the competency map from uploaded chunks. Updates baseline readiness. |
| `prep.get_readiness` | Latest 7-dim deterministic readiness snapshot. |
| `prep.start_session` | Open a `mock_interview` or `final_boss` session. |
| `prep.next_question` | Examiner picks the next competency + difficulty, returns a grounded question. Idempotent per turn. |
| `prep.submit_answer` | Evaluator scores → Weakness updates → Adaptive Planner decides next move → readiness recompute. |
| `prep.finish_session` | Close the session, produce the final readiness report. |

### Lab mount

`POST /api/v1/mcp-lab/` — mirrors the 7 tools (direct delegates to the judged implementations, no behavioural drift) plus `prep.debug.resolve_provider` for inspecting per-request provider resolution. Accepts an `X-LLM-Provider: mock|openai|bedrock` header for per-call provider override.

### REST (web + admin)

Mounted under `/api/v1/`:

- `auth/`: register, login, me, forgot-password, reset-password
- `projects/{id}/{documents,competencies,readiness,sessions,retrieve}`: the preparation primitives
- `sessions/{id}/turns`: the turn-based interview loop
- `admin/{providers,smtp,announcements}`: admin-only, gated by `settings.admin_emails`
- `announcements/`: public read of active notices
- `alexa/`: classic Alexa webhook (fallback demo surface, not the judged path)
- `demo/seed`: no-login demo bootstrap

## Agents

Every agent conforms to the `Agent` contract in `app/agents/base.py`: `execute(ctx: AgentContext, tools: dict) -> AgentResult` with a `status`, `confidence`, `result`, and `warnings`.

| Agent | Deterministic core | Optional LLM path |
|---|---|---|
| **Document** | Text extraction + chunking from PDF / DOCX / TXT / MD. | — |
| **Knowledge Extraction** | Regex/keyword extraction of skills, technologies, metrics, claims, roles. Deterministic, dedup by `(kind, label)`. | Optional LLM enrichment via `prepend` tool arg. |
| **Examiner** | Weighted candidate pick (low mastery + high weakness + uncovered + confidence) → templated question per §24 difficulty ladder. | When `tools["llm_provider"]` is non-mock, rephrases the templated question into natural interviewer prose. Silent fallback. |
| **Evaluator** | Seven-dimension rubric scoring (accuracy, completeness, relevance, conciseness, evidence, communication, response-time) with §26 mode-specific weights. | When non-mock, attaches a 1–2 sentence `rationale` field via LLM. Scores remain deterministic. |
| **Weakness** | EMA severity per dimension bucket (knowledge, communication, evidence, pressure). | — |
| **Adaptive Planner** | §17 next-move picker: increase-difficulty / follow-up / probe-concept / coach-intervention / finish. | — |
| **Coach** | Hint templates per weakness bucket. Disabled in Final Boss. | — |

## Providers

`app/providers/` defines `LLMProvider` and `EmbeddingProvider` abstract bases.

- `mock.MockLLMProvider` / `MockEmbeddingProvider`. SHA-seeded deterministic text + unit-length vectors. **Default.** Zero API cost, tests use it, demo works offline.
- `openai_provider.OpenAILLMProvider` / `OpenAIEmbeddingProvider`. thin wrappers around the official `openai` SDK (Chat Completions + Embeddings).
- `bedrock.BedrockLLMProvider` / `BedrockEmbeddingProvider`. `boto3.bedrock-runtime` via `converse` (Anthropic, Meta, Titan, Mistral, Cohere) and `invoke_model` for Titan / Cohere embeddings.

Two resolver paths:

- `app/providers/__init__.py:get_llm_provider`: `lru_cache`-backed, reads `settings.llm_provider`. Used by the judged MCP mount, REST endpoints, and the Alexa webhook.
- `app/providers/router.py:resolve_providers(ctx, session, scope="lab")`: per-request resolver: `X-LLM-Provider` header → DB `provider_configs` row → settings. Used by the lab MCP mount so admins (and judges) can switch providers without a server restart.

## Persistence

Postgres 16 + pgvector; migrations via Alembic. Six revisions in `backend/alembic/versions/`:

1. `baf7a8eff1f9`. users, projects, documents
2. `7e3c336989c5`. document chunks (and later-fixed embedding column)
3. `b2d5f7e8a002`. add `embedding` column that was missing from the previous migration
4. `a1c2e4d6f001`. competency items, sessions, turns, weakness records, readiness snapshots
5. `c3e7f9a1b003`. provider configs (admin-editable `lab` scope + mirror `judged` scope)
6. `d4a1b2c3e004`. SMTP configs, announcements, password reset tokens

The backend container auto-runs `alembic upgrade head` on start, so a judge's `docker compose up` on a fresh clone needs no DB setup step.

## Infrastructure

- **Local dev:** `docker compose up --build` (Postgres, Redis, MinIO, backend, frontend). Backend binds `:8000`, frontend `:3000`.
- **Prod:** VPS with a `docker-compose.override.yml` that rebinds containers to localhost-only ports and drops dev bind-mounts, behind nginx + Let's Encrypt TLS.
- **Tests:** 108 passing. `pytest` runs in-container against the real Postgres + MinIO.

## Design decisions worth preserving

- **Deterministic by default.** The LLM is an enhancement, not a dependency. Tests stay reproducible; demos work offline; nothing breaks when a provider errors.
- **Judged mount is frozen.** Experimentation lives on the lab mount (`/api/v1/mcp-lab/`). The judged `app/mcp/server.py` is byte-identical between demos.
- **Readiness is a function, not a prompt.** `app/readiness.py` computes the overall + per-dimension scores from the mastery table, dimension history, difficulty curve, and weakness penalties. Same inputs always produce the same output.
- **Admin UI never writes API keys.** Keys live in `.env`. The admin dashboard picks provider *names* (`mock` / `openai` / `bedrock`) and *model names*; the server reads the key from env when it calls out.
