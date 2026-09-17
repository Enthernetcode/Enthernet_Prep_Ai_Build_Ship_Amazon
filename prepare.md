# prepare.md

Operational preparation notes for humans running Enthernet Prep AI locally or in CI.

## Local

1. `cp .env.example .env`
2. `docker compose up --build`
3. Verify: `curl -s localhost:8000/api/v1/health` returns `{"status":"ok","db":"ok"}`.

## Backend commands

```bash
docker compose exec backend pytest
docker compose exec backend alembic upgrade head
docker compose exec backend alembic revision --autogenerate -m "msg"
docker compose exec backend ruff check .
```

## Frontend commands

```bash
docker compose exec frontend npm run lint
docker compose exec frontend npm run build
```

## Provider keys

Fill at least one LLM provider key in `.env` before running any agent code. The scaffold does not exercise any provider yet.

## Reset local state

```bash
docker compose down -v   # drops postgres + minio volumes
```
