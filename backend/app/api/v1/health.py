from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/health")


@router.get("/livez")
async def livez() -> dict[str, str]:
    """Liveness — process is up. No dependency checks; safe for high-frequency
    uptime pings and cheap enough to never rate-limit."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Readiness — process is alive AND its critical dependencies work.
    Returns 200 when Postgres answers `SELECT 1`, otherwise 503 with a
    machine-readable `db` field."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "db": "error"}
    return {"status": "ok", "db": "ok"}


@router.get("")
async def health(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Back-compat: original /api/v1/health endpoint."""
    db_ok = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = "error"
    return {"status": "ok", "db": db_ok}
