from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter()


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    db_ok = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = "error"
    return {"status": "ok", "db": db_ok}
