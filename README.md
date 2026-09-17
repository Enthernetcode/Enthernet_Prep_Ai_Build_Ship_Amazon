# Enthernet Prep AI

**Live in the Moment.**

Agentic AI readiness engine — turns user-uploaded material (CVs, JDs, decks, notes) into personalized, adaptive practice with quantified readiness scoring. Web + Alexa+.

See [`AGENT.md`](./AGENT.md) for the full implementation contract.

## Repo layout

```
backend/       FastAPI service — agents, API, workers land here
frontend/      Next.js (App Router) — dashboard + session UI
db/            Postgres init scripts (pgvector extension)
docs/          Architecture, security, Alexa+, evaluation
```

## Quickstart (local dev)

Prereqs: Docker + Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Then:

- API health: <http://localhost:8000/api/v1/health>
- API docs:   <http://localhost:8000/docs>
- Frontend:   <http://localhost:3000>
- MinIO UI:   <http://localhost:9001> (user/pass from `.env`)

Run backend tests:

```bash
docker compose exec backend pytest
```

Create a migration (once models exist):

```bash
docker compose exec backend alembic revision --autogenerate -m "your message"
docker compose exec backend alembic upgrade head
```

## Status

Scaffold only. Auth, agents, document pipeline, and Alexa+ adapter land next — see `AGENT.md` §73 for build order.
